"""Bonfire fog overlay: analyse and patch DSR FFX (FXR1, x64 "wide" variant) in the sfx bnd.

Usage:
  python tools/fog_ffx.py analyse [ids...]           # default ids: 90012 90016 90015 90010
  python tools/fog_ffx.py build [--widen-id 90010] [--factor 1.06] [--test-ids 90012 90010]

build writes into tools/out/:
  FRPG_SfxBnd_CommonEffects.ffxbnd.dcx     widened: X-scale floats of --widen-id multiplied in place
  fog_test_empty_<id>.ffxbnd.dcx           test: f<id>.ffx replaced by f0090005.ffx (empty), id patched
Each output is re-read and checked: entry count/names/ids equal, only the intended bytes differ.

FXR1 wide layout (DSR, after SoulsFormatsNEXT FXR1): header +0x08 main offset (0x30), +0x10 metadata
offset, +0x14 pointer count, +0x18 node count; metadata = pointer locations (u64) then node offsets.
Every pointer/varint is 8 bytes (int32 + 0 / 0xCDCDCDCD). Action data block: i32 type, i32 size,
varint resCount, ptr resNumbers, ptr resNodes, ptr parentContainer, then type-specific body (+0x28).
FXField = varint type + ptr data; types 24 const f32, 25 base/min/max, 0/4/12/16 ticks
(i32 n, n times, n values), 5/17 ticks+min/max, 6 ticks+res, 7 ticks+min/max+res, 28 empty.
"""
import argparse, os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
from fromsoft.containers import dcx_decompress, dcx_compress, bnd3_read, bnd3_write, bnd3_raw_entries

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'local/game', 'sfx', 'FRPG_SfxBnd_CommonEffects.ffxbnd.dcx')
OUT = os.path.join(ROOT, 'tools', 'out')
EMPTY_ID = 90005
ACTION_TYPES = (27, 28, 29, 30, 31, 32, 40, 43, 55, 59, 61, 66, 70, 71, 84, 105, 107, 108, 117)

# Body layouts (offsets relative to block +0x28). 'F' = FXField (16 bytes), 'f' f32, 'i' i32.
_S = lambda names: ['F:' + n for n in names.split()]
LAYOUT = {
    43: ['f:Unk1', 'i:0', 'i:0', 'i:Tex1', 'i:Tex2', 'i:DistMode', 'i:Shape', 'i:Orient', 'i:Blend', 'i:pad']
        + _S('ScaleX ScaleY ScaleZ Stretch Intensity WobSpeed WobRadius WaveSpeed FlowSpeed R G B A'),
    59: ['f:Unk1', 'i:0', 'i:TexID', 'i:0', 'i:Orient', 'i:Blend'] + _S('ScaleX ScaleY RotX RotY RotZ')
        + ['i:SliceRow', 'i:FrameTotal'] + _S('AnimInit AnimTL UVShiftX UVShiftY R G B A'),
    70: ['f:Duration', 'f:DurMult', 'f:LifeVar', 'i:Attached', 'f:RenderDepth', 'i:0', 'i:Tex1', 'i:Tex2',
         'i:Tex3', 'i:Orient', 'i:Blend', 'i:Unk8']
        + _S('Scale1X Scale1Y Scale2X Scale2Y RotX RotY RotZ RotSpdX RotSpdY RotSpdZ T1OffX T1OffY T1ScrX '
             'T1ScrY T2OffX T2OffY T2ScrX T2ScrY T3OffX T3OffY T3ScrX T3ScrY C1R C1G C1B C1A C2R C2G C2B C2A'),
    71: ['f:Duration', 'f:DurMult', 'f:LifeVar', 'i:Attached', 'f:RenderDepth', 'i:0', 'i:TexID', 'i:Unk7',
         'i:Orient', 'i:Blend', 'i:Unk10', 'i:0']
        + _S('Scale1X Scale1Y Scale2X Scale2Y RotX RotY RotZ RotSpdX RotSpdY RotSpdZ')
        + ['i:SliceRow', 'i:FrameTotal'] + _S('AnimInit AnimTL C1R C1G C1B C1A C2R C2G C2B C2A'),
}
# Width field per appearance type: a field that scales X only (Scale2X for 70/71: its Y partner is a
# separate field, while an empty Scale1Y may mean "same as Scale1X"). Fallback: the first X field.
WIDTH_FIELDS = {43: ['ScaleX'], 59: ['ScaleX'], 70: ['Scale2X', 'Scale1X'], 71: ['Scale2X', 'Scale1X']}


class Ffx:
    def __init__(self, data):
        if data[:4] != b'FXR\0':
            raise ValueError('not FXR1')
        self.d = data
        self.meta, self.nptr, self.nnode = struct.unpack_from('<III', data, 0x10)
        self.ptrs = [struct.unpack_from('<Q', data, self.meta + 8 * i)[0] for i in range(self.nptr)]
        self.ptrset = set(self.ptrs)
        self.root_id = self.i32(0x38)

    def i32(self, o): return struct.unpack_from('<i', self.d, o)[0]
    def f32(self, o): return struct.unpack_from('<f', self.d, o)[0]

    def action_datas(self):
        """[(offset, type)] of action-data blocks (type, size, then 3 pointers at +0x10/+0x18/+0x20)."""
        out = []
        for o in range(0x30, self.meta, 8):
            t, size = struct.unpack_from('<ii', self.d, o)
            if t in ACTION_TYPES and 0 < size < 0x4000 and {o + 0x10, o + 0x18, o + 0x20} <= self.ptrset:
                out.append((o, t))
        return out

    def field(self, at):
        """FXField at `at` -> dict(type, data, floats=[(offset, value)] that hold the field's values)."""
        t, off = self.i32(at), self.i32(at + 8)
        f = {'at': at, 'type': t, 'data': off, 'floats': [], 'text': ''}
        if t == 28:
            f['text'] = 'empty'
        elif t == 24:
            f['floats'] = [(off, self.f32(off))]
            f['text'] = f'const {self.f32(off):g}'
        elif t == 25:
            b, lo, hi = struct.unpack_from('<3f', self.d, off)
            f['floats'] = [(off, b)]
            f['text'] = f'base {b:g} min {lo:g} max {hi:g}'
        elif t in (0, 4, 5, 6, 7, 12, 16, 17):
            n = self.i32(off)
            ts = struct.unpack_from(f'<{n}f', self.d, off + 4)
            f['floats'] = [(off + 4 + 4 * n + 4 * k, self.f32(off + 4 + 4 * n + 4 * k)) for k in range(n)]
            f['text'] = f'seq{t} ' + ' '.join(f'{tm:g}:{v:g}' for tm, (_, v) in zip(ts, f['floats']))
            if t in (5, 7, 17):
                f['text'] += ' min/max %g/%g' % struct.unpack_from('<2f', self.d, off + 4 + 8 * n)
        else:
            f['text'] = f'type {t} (not decoded)'
        return f

    def body(self, o, t):
        """Decode the body of appearance block (o, t) -> {name: value or field dict}."""
        res, p = {}, o + 0x28
        for k in LAYOUT[t]:
            kind, name = k.split(':')
            if kind == 'F':
                res[name] = self.field(p); p += 16
            else:
                res[name] = self.f32(p) if kind == 'f' else self.i32(p); p += 4
        return res

    def refs_to(self, off):
        """Pointer locations whose target is `off`."""
        return [loc for loc in self.ptrs if struct.unpack_from('<Q', self.d, loc)[0] == off]


def ffx_ids_called(ffx):
    """Effect ids referenced by effect-call nodes (tag 37, id at +8)."""
    ids = set()
    for k in range(ffx.nnode):
        o = struct.unpack_from('<Q', ffx.d, ffx.meta + 8 * ffx.nptr + 8 * k)[0]
        if ffx.i32(o) == 37 and ffx.i32(o + 8):
            ids.add(ffx.i32(o + 8))
    return sorted(ids)


def width_patches(ffx, factor):
    """[(float_offset, old, new, label)] for the width field of every appearance block in `ffx`."""
    patches = []
    for o, t in ffx.action_datas():
        if t not in WIDTH_FIELDS:
            continue
        body = ffx.body(o, t)
        for name in WIDTH_FIELDS[t]:
            f = body[name]
            if f['floats']:
                break
        else:
            continue
        for off, v in f['floats']:
            # The value must belong to this field only (no other field or node points at it).
            others = [loc for loc in ffx.refs_to(f['data']) if loc != f['at'] + 8 and not (
                loc in (o + 0x10, o + 0x18) and ffx.i32(o + 8) == 0)]
            if others:
                raise ValueError(f'f{ffx.root_id:07d} {t}@{o:#x} {name}: data shared with {others}')
            patches.append((off, v, v * factor, f'action {t} @{o:#x} {name}'))
    return patches


def analyse(entries, ids):
    by_id = {name_id(n): d for _i, n, d in entries if n.endswith('.ffx')}
    for fid in ids:
        ffx = Ffx(by_id[fid])
        print(f'== f{fid:07d}.ffx  size {len(ffx.d)}  root id {ffx.root_id}  calls {ffx_ids_called(ffx)}')
        for o, t in ffx.action_datas():
            if t not in LAYOUT:
                print(f'  action {t} @{o:#x}')
                continue
            print(f'  action {t} @{o:#x}')
            for k, v in ffx.body(o, t).items():
                if isinstance(v, dict):
                    if v['type'] != 28:
                        print(f'    {k:12} @{v["at"]:#06x} -> {v["data"]:#06x}  {v["text"]}')
                elif k not in ('0', 'pad'):
                    print(f'    {k:12} {v:g}' if isinstance(v, float) else f'    {k:12} {v}')


def name_id(name):
    stem = name.replace('\\', '/').rsplit('/', 1)[-1]
    return int(stem[1:].split('.')[0]) if stem.startswith('f') and stem.endswith('.ffx') else None


def write_checked(path, raw_src, plain_src, entries, new_datas, expect):
    """Build, write and verify one output. expect = {entry_index: set(changed byte offsets) or None (any)}."""
    plain = bnd3_write(plain_src, new_datas)
    raw = dcx_compress(plain, raw_src)
    with open(path, 'wb') as fh:
        fh.write(raw)
    back = bnd3_raw_entries(dcx_decompress(open(path, 'rb').read()))
    assert len(back) == len(entries), 'entry count changed'
    for k, ((i0, n0, d0), (i1, n1, d1)) in enumerate(zip(entries, back)):
        assert (i0, n0) == (i1, n1), f'entry {k} id/name changed'
        if k not in expect:
            assert d0 == d1, f'entry {k} ({n0}) changed unexpectedly'
        elif expect[k] is not None:
            assert len(d0) == len(d1), f'entry {k} size changed'
            diff = {j for j in range(len(d0)) if d0[j] != d1[j]}
            assert diff <= expect[k] and diff, f'entry {k}: unexpected bytes {sorted(diff - expect[k])}'
        else:
            assert d1 == new_datas[k]
    print(f'  wrote {os.path.relpath(path, ROOT)}  {len(raw):,} B (plain {len(plain):,} B), verified')


def build(entries, raw_src, plain_src, widen_id, factor, test_ids):
    os.makedirs(OUT, exist_ok=True)
    datas = [d for _i, _n, d in entries]
    index = {name_id(n): k for k, (_i, n, _d) in enumerate(entries) if n.endswith('.ffx')}
    # Sanity: an unchanged rebuild must reproduce the original archive byte for byte.
    assert bnd3_write(plain_src, datas) == plain_src, 'BND3 rebuild is not byte-identical'

    for tid in test_ids:
        empty = bytearray(datas[index[EMPTY_ID]])
        struct.pack_into('<i', empty, 0x38, tid)       # keep the effect id the game asks for
        new = list(datas)
        new[index[tid]] = bytes(empty)
        print(f'test: f{tid:07d}.ffx -> f{EMPTY_ID:07d}.ffx (root id patched to {tid})')
        write_checked(os.path.join(OUT, f'fog_test_empty_{tid}.ffxbnd.dcx'), raw_src, plain_src, entries,
                      new, {index[tid]: None})

    k = index[widen_id]
    ffx = Ffx(datas[k])
    patches = width_patches(ffx, factor)
    buf = bytearray(datas[k])
    changed = set()
    print(f'widen: f{widen_id:07d}.ffx x{factor}')
    for off, old, new, label in patches:
        struct.pack_into('<f', buf, off, new)
        changed |= set(range(off, off + 4))
        print(f'  {label:28} float @{off:#06x}: {old:g} -> {struct.unpack_from("<f", buf, off)[0]:g}')
    new = list(datas)
    new[k] = bytes(buf)
    write_checked(os.path.join(OUT, 'FRPG_SfxBnd_CommonEffects.ffxbnd.dcx'), raw_src, plain_src, entries,
                  new, {k: changed})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['analyse', 'build'])
    ap.add_argument('ids', nargs='*', type=int, default=[90012, 90016, 90015, 90010])
    ap.add_argument('--widen-id', type=int, default=90010)
    ap.add_argument('--factor', type=float, default=1.06)
    ap.add_argument('--test-ids', type=int, nargs='*', default=[90012, 90010])
    a = ap.parse_args()
    raw_src = open(SRC, 'rb').read()
    plain_src = dcx_decompress(raw_src)
    entries = bnd3_raw_entries(plain_src)
    if a.cmd == 'analyse':
        analyse(entries, a.ids)
    else:
        build(entries, raw_src, plain_src, a.widen_id, a.factor, a.test_ids)


if __name__ == '__main__':
    main()
