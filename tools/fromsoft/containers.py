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


def _bnd3_layout(buf):
    """Return (endian, fmt, entry_size, [(entry_pos, size_pos, off_pos, usize_pos)]) of a plain BND3."""
    big = buf[0xd] != 0
    fmt = _bnd3_format(buf[0xc], buf[0xe] != 0)
    e = '>' if big or fmt & 1 else '<'
    count, = struct.unpack_from(e + 'i', buf, 0x10)
    esize = 12 + (4 if fmt & 0x10 else 0) + (4 if fmt & 2 else 0) + (4 if fmt & 0xc else 0) + (4 if fmt & 0x20 else 0)
    slots = []
    for i in range(count):
        pos = 0x20 + i * esize
        slots.append((pos, pos + 4, pos + 8, pos + esize - 4 if fmt & 0x20 else None))
    return e, fmt, esize, slots


def bnd3_write(plain, datas, align=16):
    """Rebuild a plain (non-DCX) BND3: keep header, entry table and names byte-identical, replace the
    entry data by `datas` (raw bytes, same order) and re-lay it out with `align` padding (zeros).
    With unchanged datas this reproduces the original file for archives laid out that way (DS1 sfx bnds)."""
    if plain[:4] != b'BND3':
        raise ValueError('not BND3')
    e, fmt, _esize, slots = _bnd3_layout(plain)
    if fmt & 0x10:
        raise ValueError('LongOffsets BND3 not supported')
    if len(datas) != len(slots):
        raise ValueError('entry count mismatch')
    first = min(struct.unpack_from(e + 'I', plain, s[2])[0] for s in slots)
    out = bytearray(plain[:first])
    for (_pos, size_pos, off_pos, usize_pos), data in zip(slots, datas):
        out += b'\0' * (-len(out) % align)
        struct.pack_into(e + 'iI', out, size_pos, len(data), len(out))
        if usize_pos is not None:
            struct.pack_into(e + 'i', out, usize_pos, len(data))
        out += data
    return bytes(out)


def bnd3_raw_entries(plain):
    """Plain BND3 -> list of (id, name, raw_bytes) without decompressing nested DCX entries."""
    e, _fmt, _esize, slots = _bnd3_layout(plain)
    out = []
    for (_pos, size_pos, _off_pos, _u), (fid, name, _d) in zip(slots, bnd3_read(plain)):
        size, off = struct.unpack_from(e + 'iI', plain, size_pos)
        out.append((fid, name, plain[off:off + size]))
    return out


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
