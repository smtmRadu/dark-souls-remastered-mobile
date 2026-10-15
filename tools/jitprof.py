"""jitprof.py REPORT PERFMAP: attribute simpleperf samples in Box64 JIT code to game (x86) functions.

REPORT : output of `simpleperf report -i X --sort symbol --percent-limit 0` (lines like "1.10%  unknown[+760c0a1f8c]")
PERFMAP: Box64 perf map (BOX64_DYNAREC_PERFMAP=1 -> /tmp/perf-<pid>.map, lines "<native start> <size> <name with x86 addr>")
Prints the hottest game functions (from the exe's .pdata) and the share that stays unresolved.
"""
import bisect, collections, re, struct, sys
import pefile

EXE = "Dark.Souls.Remastered.v1.04/DarkSoulsRemastered.exe"


def load_map(path):
    blocks = []
    for line in open(path, errors="replace"):
        p = line.split(None, 2)
        if len(p) < 3:
            continue
        try:
            start, size = int(p[0], 16), int(p[1], 16)
        except ValueError:
            continue
        m = re.search(r"0x([0-9a-fA-F]+)", p[2])
        blocks.append((start, size, int(m.group(1), 16) if m else None, p[2].strip()))
    blocks.sort()
    return blocks


def load_funcs():
    pe = pefile.PE(EXE, fast_load=True)
    pd = [s for s in pe.sections if s.Name.startswith(b".pdata")][0].get_data()
    fs = []
    for i in range(0, len(pd), 12):
        b, e, _ = struct.unpack_from("<III", pd, i)
        if b == 0:
            break
        fs.append((0x140000000 + b, 0x140000000 + e))
    fs.sort()
    return fs


def main(report, perfmap):
    blocks = load_map(perfmap)
    starts = [b[0] for b in blocks]
    funcs = load_funcs()
    fstarts = [f[0] for f in funcs]
    per_func, per_other = collections.Counter(), collections.Counter()
    total = unresolved = 0.0
    for line in open(report, errors="replace"):
        m = re.match(r"\s*([\d.]+)%\s+(.*)$", line)
        if not m:
            continue
        pct, sym = float(m.group(1)), m.group(2).strip()
        total += pct
        u = re.search(r"unknown\[\+([0-9a-f]+)\]", sym)
        if not u:
            per_other[sym] += pct
            continue
        ip = int(u.group(1), 16)
        k = bisect.bisect_right(starts, ip) - 1
        if k < 0 or ip >= blocks[k][0] + blocks[k][1] or blocks[k][2] is None:
            unresolved += pct
            continue
        x86 = blocks[k][2]
        j = bisect.bisect_right(fstarts, x86) - 1
        if j >= 0 and x86 < funcs[j][1]:
            per_func[funcs[j][0]] += pct
        else:
            per_func[x86 & ~0xFFF] += pct  # not in the exe's .pdata (other module / Arxan): group by page
    print(f"total {total:.1f}%  unresolved JIT {unresolved:.1f}%")
    print("== hottest game functions (x86 start, % of game-process cycles)")
    for f, p in per_func.most_common(40):
        print(f"  {f:x}  {p:5.2f}%")
    print("== native symbols")
    for s, p in per_other.most_common(15):
        print(f"  {p:5.2f}%  {s}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
