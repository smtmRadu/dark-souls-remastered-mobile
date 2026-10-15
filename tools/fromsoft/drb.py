"""DRB (menu layout, DS1 / DSR PC) reader: just enough to get named Sprite shapes.

Layout: 'DRB\\0' + 12 pad, then chunks [magic(4) size(i32) count(i32) pad(4)] + data:
  STR   UTF-16LE strings; every name/type offset below is relative to its data start
  TEXI  16-byte entries: nameOff, pathOff, 0, 0 (texture index -> texture name)
  SHPR  raw shape parameter blob
  SHAP  8-byte entries: typeOff ('Sprite', 'Text', 'Null' ...), offset into SHPR
  DLGO  32-byte entries: nameOff, offset into SHAP, offset into CTRL, ...
Sprite params in SHPR come in two layouts:
  PTDE (loose menu.drb, 28 bytes): screen rect L,T,R,B (i16 x4), texture rect L,T,R,B (i16 x4),
       texture index (i16), flags (i16), 0 (i32), colour (i32). Texture rects are in PTDE (half) resolution.
  DSR  (menu.drb.dcx, 36 bytes): screen rect (i16 x4), scaling origin X,Y (i16 x2, usually -1), scaling type (i32),
       then the same texture rect / index / flags / 0 / colour. Texture rects match the DSR atlases.
The layout is detected by which offset holds a plausible (texture index, flags=0x100) pair for most sprites.
"""
import struct
from .containers import dcx_decompress


def _chunks(buf):
    out, p = {}, 0x10
    while p < len(buf):
        magic = buf[p:p + 4].rstrip(b'\0').decode()
        size, count = struct.unpack_from('<ii', buf, p + 4)
        out[magic] = (p + 0x10, count)
        if magic == 'END':
            break
        p += 0x10 + size
    return out


def drb_sprites(buf):
    """-> (is_dsr_layout, [(dialog_object_name, texture_name, (left, top, right, bottom))]) for every Sprite."""
    buf = dcx_decompress(buf)
    if buf[:4] != b'DRB\0':
        raise ValueError('not DRB')
    ch = _chunks(buf)
    str0 = ch['STR'][0]

    def s(off):
        end = str0 + off
        while buf[end:end + 2] != b'\0\0':
            end += 2
        return buf[str0 + off:end].decode('utf-16-le')

    texi0, ntex = ch['TEXI']
    textures = [s(struct.unpack_from('<i', buf, texi0 + 16 * i)[0]) for i in range(ntex)]
    dlgo0, ndlgo = ch['DLGO']
    sprites = []                             # (name, SHPR position) of every Sprite shape
    for i in range(ndlgo):
        name_off, shap_off = struct.unpack_from('<ii', buf, dlgo0 + 32 * i)
        type_off, shpr_off = struct.unpack_from('<ii', buf, ch['SHAP'][0] + shap_off)
        if s(type_off) == 'Sprite':
            sprites.append((s(name_off), ch['SHPR'][0] + shpr_off))

    def plausible(tex_rect_at):
        return sum(1 for _n, p in sprites
                   if struct.unpack_from('<hh', buf, p + tex_rect_at + 8)[1] == 0x100)
    dsr = plausible(16) > plausible(8)
    at = 16 if dsr else 8                    # offset of the texture rect inside the sprite params
    out = []
    for name, p in sprites:
        rect = struct.unpack_from('<4h', buf, p + at)
        tex, = struct.unpack_from('<h', buf, p + at + 8)
        if 0 <= tex < ntex:
            out.append((name, textures[tex], rect))
    return dsr, out
