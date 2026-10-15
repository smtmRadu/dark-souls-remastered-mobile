"""xref.py ADDR [ADDR...]: direct callers (E8/E9), qword refs and .pdata function bounds for DSR exe addresses; disasm context."""
import sys, struct, pefile, capstone
pe = pefile.PE("Dark.Souls.Remastered.v1.04/DarkSoulsRemastered.exe", fast_load=True); d = pe.__data__
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
off = lambda va: pe.get_offset_from_rva(va - 0x140000000)
pd = [s for s in pe.sections if s.Name.startswith(b".pdata")][0].get_data()
def fn(va):
    r = va - 0x140000000
    for i in range(0, len(pd), 12):
        b, e, u = struct.unpack_from("<III", pd, i)
        if b <= r < e: return 0x140000000 + b, 0x140000000 + e
texts = [s for s in pe.sections if s.Name.startswith(b".text")]
def callers(t):
    out = []
    for s in texts:
        data = s.get_data()
        for k in range(len(data) - 5):
            if data[k] in (0xE8, 0xE9) and s.VirtualAddress + k + 5 + struct.unpack_from("<i", data, k + 1)[0] == t - 0x140000000:
                out.append(0x140000000 + s.VirtualAddress + k)
    return out
def ctx(a, before=0x40, after=0x10):
    for i in md.disasm(d[off(a) - before:off(a) + after], a - before):
        print("    %x %s %s" % (i.address, i.mnemonic, i.op_str))
if __name__ == "__main__":
    for a in sys.argv[1:]:
        t = int(a, 16); f = fn(t)
        print("== %x in func %s" % (t, f and (hex(f[0]), hex(f[1]))))
        for c in callers(f[0] if f else t):
            print("  caller %x in %s" % (c, fn(c) and hex(fn(c)[0]))); ctx(c)
