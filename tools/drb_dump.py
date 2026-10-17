"""drb_dump.py PREFIX [DRB_DCX]: print every object of the DRB dialogs whose name starts with PREFIX.

One line per object: dialog, object, shape type, rect L,T,R,B, scaling origin + type; Dialog shapes add the child
dialog name, Text shapes the font (+0x1c) and alignment (+0x1e). Default file: the stock game menu.drb.dcx.
"""
import os, struct, sys
from fromsoft.containers import dcx_decompress
from fromsoft.drb import _chunks

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    prefix = sys.argv[1]
    path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, '..', 'local', 'game', 'menu', 'menu.drb.dcx')
    buf = dcx_decompress(open(path, 'rb').read())
    ch = _chunks(buf)
    str0 = ch['STR'][0]

    def s(off):
        end = str0 + off
        while buf[end:end + 2] != b'\0\0':
            end += 2
        return buf[str0 + off:end].decode('utf-16-le')

    dlg0, ndlg = ch['DLG']
    names = [s(struct.unpack_from('<i', buf, dlg0 + 0x40 * i)[0]) for i in range(ndlg)]
    dlgo0, shap0, shpr0 = ch['DLGO'][0], ch['SHAP'][0], ch['SHPR'][0]
    for i in range(ndlg):
        if not names[i].startswith(prefix):
            continue
        e = dlg0 + 0x40 * i
        count, first = struct.unpack_from('<ii', buf, e + 0x20)
        print('%s  own rect %s' % (names[i], struct.unpack_from('<4h', buf, e + 0x28)))
        for k in range(count):
            name_off, shap_off = struct.unpack_from('<ii', buf, dlgo0 + first + 32 * k)
            st = s(struct.unpack_from('<i', buf, shap0 + shap_off)[0])
            if st == 'Null':   # Null: a rect only (hit rects of rows / buttons)
                p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
                print('   %-28s Null         %s' % (s(name_off), struct.unpack_from('<4h', buf, p)))
                continue
            p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
            r = struct.unpack_from('<4h', buf, p)
            ox, oy, sty = struct.unpack_from('<2hi', buf, p + 8)
            extra = ''
            if st == 'Dialog':
                d = struct.unpack_from('<H', buf, p + 0x10)[0]
                extra = '-> ' + (names[d] if d < ndlg else names[d // 0x40] if d % 0x40 == 0 and d // 0x40 < ndlg else '?%d' % d)
            elif st == 'Text':
                extra = 'font %d align 0x%02x' % (buf[p + 0x1c], buf[p + 0x1e])
            print('   %-28s %-12s %-26s o(%d,%d) t%d %s' % (s(name_off), st, r, ox, oy, sty, extra))


if __name__ == '__main__':
    main()
