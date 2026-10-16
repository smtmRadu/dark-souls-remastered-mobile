"""dark_splash.py [GAME_DIR] [OUT_FILE]: dark mode for the Bandai Namco splash (user 2026-10-16: "I hate that white").

The splash is texture Logo_02 in menu/menu_2.tpf.dcx: DXT1, 4096x2048 (+ mips), logo on white. The other splash
textures (FromSoftware, Havok) are already on black.

Method (DXT1 blocks edited in place, the DDS keeps its size, so the TPF is patched in place):
1. Decode mip 0. Background mask = near-white pixels, except the enclosed white inside the orange / yellow blob's
   bounding box (the white BANDAI NAMCO letters). Holes in the red "Entertainment" letters become black too.
2. Per block: all background -> solid black. Background + logo (antialiased logo edge) -> each endpoint loses its
   white part (c - min(r, g, b) per channel), so the edge blends to black. No background -> unchanged.
   Endpoint order sets the block mode (c0 > c1: 4 colours, else 3 colours + transparent): swapped endpoints get
   their indices remapped.
3. Mip levels use the mask scaled down (a block is background only if all its source pixels are).
Output: out/menu_2.tpf.dcx (push to <game>/menu/menu_2.tpf.dcx).
"""
import io
import os
import struct
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fromsoft.containers import dcx_compress, dcx_decompress  # noqa: E402

WHITE_MIN = 200   # all channels >= this = "white" for the background flood fill


def unpack565(c):
    return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31


def pack565(r, g, b):
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def unwhite(c):
    r, g, b = unpack565(c)
    m = min(r, g, b)
    return pack565(r - m, g - m, b - m)


def remap(idx, table):
    return sum(table[(idx >> (2 * i)) & 3] << (2 * i) for i in range(16))


def edge_block(c0, c1, idx):
    n0, n1 = unwhite(c0), unwhite(c1)
    four = c0 > c1
    if n0 == n1:
        return n0, n0, 0
    if four != (n0 > n1):
        n0, n1 = n1, n0
        idx = remap(idx, [1, 0, 3, 2] if four else [1, 0, 2, 3])
    return n0, n1, idx


def _border_flood(white):
    """White pixels 4-connected to the image border (flood fill by iterative dilation)."""
    bg = np.zeros_like(white)
    bg[0, :], bg[-1, :], bg[:, 0], bg[:, -1] = white[0, :], white[-1, :], white[:, 0], white[:, -1]
    while True:
        grown = bg.copy()
        grown[1:, :] |= bg[:-1, :]
        grown[:-1, :] |= bg[1:, :]
        grown[:, 1:] |= bg[:, :-1]
        grown[:, :-1] |= bg[:, 1:]
        grown &= white
        if (grown == bg).all():
            return bg
        bg = grown


def background_mask(img):
    """Near-white pixels that are not the white letters of the orange blob.

    White connected to the border is background. Enclosed white (holes in the red "Entertainment" letters) is
    background too, except inside the bounding box of the orange / yellow blob (the white BANDAI NAMCO letters)."""
    a = np.asarray(img.convert('RGB')).astype(int)
    white = (a >= WHITE_MIN).all(axis=2)
    blob = (a[..., 0] > 230) & (a[..., 1] > 170) & (a[..., 2] < 60)   # the yellow outer blob (red text edges blend to orange)
    ys, xs = np.nonzero(blob)
    in_blob = np.zeros_like(white)
    in_blob[ys.min():ys.max() + 1, xs.min():xs.max() + 1] = True
    return white & ~(in_blob & ~_border_flood(white))


def patch_dds(dds):
    assert dds[:4] == b'DDS ' and dds[84:88] == b'DXT1', dds[84:88]
    h, w = struct.unpack_from('<II', dds, 12)
    mips = max(1, struct.unpack_from('<I', dds, 28)[0])
    bg = background_mask(Image.open(io.BytesIO(dds)))   # mip 0
    out = bytearray(dds)
    p = 128
    counts = [0, 0, 0]
    for level in range(mips):
        lw, lh = max(1, w >> level), max(1, h >> level)
        bw, bh = (lw + 3) // 4, (lh + 3) // 4
        s = 4 << level                     # mip-0 pixels per block side at this level
        H, W = bg.shape
        pad = np.ones((bh * s, bw * s), bool)
        pad[:min(H, bh * s), :min(W, bw * s)] = bg[:bh * s, :bw * s]
        blocks = pad.reshape(bh, s, bw, s)
        all_bg = blocks.all(axis=(1, 3))
        any_bg = blocks.any(axis=(1, 3))
        for by in range(bh):
            for bx in range(bw):
                q = p + 8 * (by * bw + bx)
                if all_bg[by, bx]:
                    struct.pack_into('<HHI', out, q, 0, 0, 0)
                    counts[0] += 1
                elif any_bg[by, bx]:
                    struct.pack_into('<HHI', out, q, *edge_block(*struct.unpack_from('<HHI', out, q)))
                    counts[1] += 1
                else:
                    counts[2] += 1
        p += bw * bh * 8
    return bytes(out), (w, h, mips, counts)


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'Dark.Souls.Remastered.v1.04')
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'out', 'menu_2.tpf.dcx')
    raw = open(os.path.join(game, 'menu', 'menu_2.tpf.dcx'), 'rb').read()
    tpf = bytearray(dcx_decompress(raw))
    assert tpf[:4] == b'TPF\0'
    count, _platform, _flag2, encoding = struct.unpack_from('<iBBB', tpf, 8)
    done = 0
    for i in range(count):
        off, size, _fmt, _cube, _mips, flags1, noff = struct.unpack_from('<IiBBBBI', tpf, 0x10 + 0x14 * i)
        if encoding == 1:
            end = noff
            while tpf[end:end + 2] != b'\0\0':
                end += 2
            name = tpf[noff:end].decode('utf-16-le')
        else:
            name = tpf[noff:tpf.index(b'\0', noff)].decode('shift_jis', 'replace')
        if name != 'Logo_02':
            continue
        assert not flags1 & 2, 'compressed TPF entry'
        new, info = patch_dds(bytes(tpf[off:off + size]))
        tpf[off:off + size] = new
        print('Logo_02 %dx%d, %d mips; blocks: %d background -> black, %d edge, %d logo kept' % (*info[:3], *info[3]))
        done += 1
    assert done == 1, 'Logo_02 not found'
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'wb').write(dcx_compress(bytes(tpf), raw))
    print('wrote', dst)


if __name__ == '__main__':
    main()
