"""DCX (compressed wrapper), BND3 (file archive) and TPF (texture pack) readers for DS1 / DSR PC.
Layouts follow SoulsFormats (JKAnderson). All readers take bytes and return plain Python data.
"""
import struct, zlib


def dcx_decompress(buf):
    """DCX DFLT: big-endian header; 'DCS' holds sizes, 'DCP' the codec, 'DCA' precedes the zlib stream.
    Returns buf unchanged when it is not DCX, so callers can pass raw files too."""
    if buf[:4] != b'DCX\0':
        return buf
    usize, csize = struct.unpack_from('>II', buf, 0x1c)
    codec = buf[0x28:0x2c]
    if codec != b'DFLT':
        raise ValueError(f'unsupported DCX codec {codec!r}')
    dca = buf.index(b'DCA\0', 0x2c)
    start = dca + struct.unpack_from('>I', buf, dca + 4)[0]  # DCA size field counts its own 8 bytes
    out = zlib.decompress(buf[start:start + csize])
    if len(out) != usize:
        raise ValueError(f'DCX size mismatch {len(out)} != {usize}')
    return out


def dcx_compress(plain, like):
    """DCX DFLT writer: reuse the header of the original DCX `like`, swap in the new sizes and zlib stream."""
    dca = like.index(b'DCA\0', 0x2c)
    head = bytearray(like[:dca + struct.unpack_from('>I', like, dca + 4)[0]])
    z = zlib.compress(plain, 9)
    struct.pack_into('>II', head, 0x1c, len(plain), len(z))
    return bytes(head) + z


def _bnd3_format(raw, bit_big_endian):
    """BND3 format byte is stored bit-reversed unless (bitBigEndian or (bit0 set and bit7 clear))."""
    if bit_big_endian or (raw & 1 and not raw & 0x80):
        return raw
    return int(f'{raw:08b}'[::-1], 2)


def bnd3_read(buf):
    """BND3 -> list of (id, name, data). Single-file (non-split) archives only."""
    buf = dcx_decompress(buf)
    if buf[:4] != b'BND3':
        raise ValueError('not BND3')
    big = buf[0xd] != 0
    fmt = _bnd3_format(buf[0xc], buf[0xe] != 0)
    e = '>' if big or fmt & 1 else '<'
    count, = struct.unpack_from(e + 'i', buf, 0x10)
    pos, files = 0x20, []
    for _ in range(count):
        csize, off = struct.unpack_from(e + 'iI', buf, pos + 4)
        pos += 12
        if fmt & 0x10:                       # LongOffsets: 64-bit data offset
            off, = struct.unpack_from(e + 'Q', buf, pos - 4); pos += 4
        fid = name = None
        if fmt & 2:
            fid, = struct.unpack_from(e + 'i', buf, pos); pos += 4
        if fmt & 0xc:
            noff, = struct.unpack_from(e + 'I', buf, pos); pos += 4
            name = buf[noff:buf.index(b'\0', noff)].decode('shift_jis', 'replace')
        if fmt & 0x20:
            pos += 4                         # uncompressed size (entries are stored raw here)
        files.append((fid, name, dcx_decompress(buf[off:off + csize])))
    return files


def tpf_read(buf):
    """TPF (PC platform) -> list of (name, format, dds_bytes)."""
    buf = dcx_decompress(buf)
    if buf[:4] != b'TPF\0':
        raise ValueError('not TPF')
    count, platform, _flag2, encoding = struct.unpack_from('<iBBB', buf, 8)
    if platform != 0:
        raise ValueError(f'TPF platform {platform} not supported (PC only)')
    out = []
    for i in range(count):
        off, size, fmt, _cube, _mips, flags1, noff, _float = struct.unpack_from('<IiBBBBIi', buf, 0x10 + i * 0x14)
        if encoding == 1:                    # UTF-16LE names
            end = noff
            while buf[end:end + 2] != b'\0\0':
                end += 2
            name = buf[noff:end].decode('utf-16-le')
        else:
            name = buf[noff:buf.index(b'\0', noff)].decode('shift_jis', 'replace')
        data = buf[off:off + size]
        if flags1 & 2:
            data = dcx_decompress(data)
        out.append((name, fmt, data))
    return out
