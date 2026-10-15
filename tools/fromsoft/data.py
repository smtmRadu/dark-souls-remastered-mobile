"""PARAMDEF, PARAM and FMG readers for DS1 / DSR PC (32-bit offset variants, little-endian).
Layouts follow SoulsFormats (JKAnderson).
"""
import struct

# Scalar paramdef types -> struct code. dummy8 / fixstr / fixstrW are raw byte runs.
_SCALAR = {'s8': 'b', 'u8': 'B', 's16': 'h', 'u16': 'H', 's32': 'i', 'u32': 'I', 'f32': 'f'}


def _cstr(b, enc='shift_jis'):
    return b.split(b'\0', 1)[0].decode(enc, 'replace').strip()


def paramdef_read(buf):
    """Binary PARAMDEF (version 104, 0xB0-byte fields) -> (param_type, [field dict]).
    Each field gets a byte 'offset' and, for bitfields, a 'bit' + 'bits' position."""
    hsize, _ver, nfields, fsize = struct.unpack_from('<hhhh', buf, 4)
    ptype = _cstr(buf[0xc:0x2c])
    fields, off = [], 0
    bit_unit = None                          # (type, byte offset, bits used) of the open bitfield unit
    for i in range(nfields):
        p = hsize + i * fsize
        itype = _cstr(buf[p + 0x40:p + 0x48])   # display type (u8, s16 ...); the internal type may be an enum name
        iname = _cstr(buf[p + 0x8c:p + 0xac])
        nbytes, = struct.unpack_from('<i', buf, p + 0x64)
        f = {'name': iname, 'type': itype}
        if ':' in iname:                     # bitfield "name:N" packs into the current unit of the same type
            f['name'], nbits = iname.split(':')[0].strip(), int(iname.split(':')[1])
            unit = nbytes                    # byte size of the underlying type
            if bit_unit and bit_unit[0] == itype and bit_unit[2] + nbits <= unit * 8:
                f.update(offset=bit_unit[1], bit=bit_unit[2], bits=nbits)
                bit_unit = (itype, bit_unit[1], bit_unit[2] + nbits)
            else:
                f.update(offset=off, bit=0, bits=nbits)
                bit_unit = (itype, off, nbits)
                off += unit
        else:
            bit_unit = None
            if '[' in iname:                 # array: "name[N]"
                f['name'] = iname.split('[')[0].strip()
            f.update(offset=off, size=nbytes)
            off += nbytes
        fields.append(f)
    return ptype, fields


def param_read(buf, fields=None):
    """DS1 PARAM: 0x30 header, 12-byte row headers (id, dataOffset, nameOffset).
    Returns (param_type, {row_id: row}); row is a dict of decoded fields when `fields` is given,
    else the raw row bytes."""
    _names, data_start, _unk1, _unk2, nrows = struct.unpack_from('<IHHHH', buf, 0)
    ptype = _cstr(buf[0xc:0x2c])
    rowsize = None
    rows = {}
    offs = [struct.unpack_from('<iII', buf, 0x30 + i * 12) for i in range(nrows)]
    if len(offs) > 1:
        rowsize = offs[1][1] - offs[0][1]
    for rid, doff, _noff in offs:
        raw = buf[doff:doff + rowsize] if rowsize else buf[doff:]
        rows[rid] = decode_row(raw, fields) if fields else raw
    return ptype, rows


def decode_row(raw, fields):
    """Scalar fields only (padding and strings are skipped)."""
    row = {}
    for f in fields:
        code = _SCALAR.get(f['type'])
        if not code or 'size' in f and f['size'] != struct.calcsize(code):
            continue
        if 'bits' in f:
            unit = {1: 'B', 2: 'H', 4: 'I'}[struct.calcsize(code)]
            v, = struct.unpack_from('<' + unit, raw, f['offset'])
            row[f['name']] = (v >> f['bit']) & ((1 << f['bits']) - 1)
        else:
            row[f['name']], = struct.unpack_from('<' + code, raw, f['offset'])
    return row


def fmg_read(buf):
    """DS1 FMG (version 1, UTF-16LE): groups of consecutive ids index a string-offset table.
    Returns {id: text}; ids whose offset is 0 have no text and are left out."""
    if buf[2] != 1 or buf[1] != 0:
        raise ValueError(f'unsupported FMG version {buf[2]} bigEndian {buf[1]}')
    ngroups, _nstrings, table = struct.unpack_from('<iii', buf, 0xc)
    out = {}
    for g in range(ngroups):
        index, first, last = struct.unpack_from('<iii', buf, 0x1c + g * 12)
        for k, sid in enumerate(range(first, last + 1)):
            so, = struct.unpack_from('<i', buf, table + (index + k) * 4)
            if so:
                end = so
                while buf[end:end + 2] != b'\0\0':
                    end += 2
                out[sid] = buf[so:end].decode('utf-16-le')
    return out
