"""stackprof.py PROF [ROOT_HEX ...]: aggregate the agent's stack samples (tools/profile.sh -> out/prof_*.txt).

Each line = "rip ret1 ret2 ..." of the game's main thread. Prints:
  - self time per function (leaf) and inclusive time per function (anywhere on the stack), exe functions from .pdata;
    addresses outside the exe are grouped as "ext:<64KB page>" (Wine/system DLLs, JIT stubs);
  - for each ROOT function (default: per-frame 0x14015ce90): the split of its time across its direct callees.
"""
import bisect, collections, struct, sys
import pefile

EXE = "local/game/DarkSoulsRemastered.exe"
NAMES = {  # known functions (re/RE_NOTES.md)
    0x14015ce90: "per-frame", 0x140137f30: "WinMain loop", 0x14024af10: "step manager", 0x14024f6b0: "InGameStep::Update",
    0x1402510d0: "ingame update", 0x14036e400: "WorldChrMan update", 0x14036f610: "chr dispatcher", 0x140758a30: "IGT update",
}


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


def main(path, roots):
    funcs = load_funcs()
    starts = [f[0] for f in funcs]

    def fn(a):
        if 0x140000000 <= a < 0x146000000:
            j = bisect.bisect_right(starts, a) - 1
            if j >= 0 and a < funcs[j][1]:
                return funcs[j][0]
            return ("exe?", a & ~0xFFF)
        return ("ext", a & ~0xFFFF)

    def name(f):
        if isinstance(f, tuple):
            return f"{f[0]}:{f[1]:x}"
        return f"{f:x}" + (f" ({NAMES[f]})" if f in NAMES else "")

    stacks = [[int(x, 16) for x in l.split()] for l in open(path) if l.strip()]
    n = len(stacks)
    self_t, incl = collections.Counter(), collections.Counter()
    child = collections.defaultdict(collections.Counter)
    for st in stacks:
        fr = [fn(a) for a in st]
        self_t[fr[0]] += 1
        for f in set(fr):
            incl[f] += 1
        for i in range(1, len(fr)):  # fr[i] calls fr[i-1]
            if fr[i] in roots:
                child[fr[i]][fr[i - 1]] += 1
    pct = lambda c: f"{100 * c / n:5.1f}%"
    print(f"{n} samples")
    print("== self (leaf) top 30")
    for f, c in self_t.most_common(30):
        print(f"  {pct(c)}  {name(f)}")
    print("== inclusive top 50")
    for f, c in incl.most_common(50):
        print(f"  {pct(c)}  {name(f)}")
    for r in roots:
        print(f"== callees of {name(r)} (inclusive {pct(incl[r])})")
        for f, c in child[r].most_common(25):
            print(f"  {pct(c)}  {name(f)}")


if __name__ == "__main__":
    rs = [int(x, 16) for x in sys.argv[2:]] or [0x14015ce90]
    main(sys.argv[1], set(rs))
