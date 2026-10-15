"""Find DSR's per-frame delta-time float on PC: scan module .data and heap regions for floats ~1/60 s."""
import ctypes, ctypes.wintypes as wt, struct, time, sys
from pcgame import Game, k32
g = Game()
class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p), ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
                ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]
def regions(maxsize=1 << 30):
    a = 0; m = MBI()
    while k32.VirtualQueryEx(g.h, ctypes.c_void_p(a), ctypes.byref(m), ctypes.sizeof(m)):
        if m.State == 0x1000 and (m.Protect & 0xCC) and not (m.Protect & 0x100) and m.RegionSize <= maxsize:  # RW committed
            yield m.BaseAddress, m.RegionSize
        a = (m.BaseAddress or 0) + m.RegionSize
        if a >= 0x7fffffffffff: break
def snap(lo, hi):
    c = {}
    for b, n in regions():
        d = g.read(b, n)
        if not d: continue
        fl = memoryview(d).cast("f") if len(d) % 4 == 0 else None
        if fl is None: continue
        for i, v in enumerate(fl):
            if lo <= v <= hi: c[b + 4 * i] = v
    return c
if __name__ == "__main__":
  lo, hi = float(sys.argv[1]), float(sys.argv[2])
  s = snap(lo, hi); print("first", len(s))
  for k in range(4):
      time.sleep(0.5)
      s = {a: v for a, v in s.items() if (x := g.f32(a)) is not None and lo <= x <= hi and x != v} if k == 0 else {a: v for a, v in s.items() if (x := g.f32(a)) is not None and lo <= x <= hi}
      print("pass", k, len(s))
  for a in list(s)[:40]:
      vals = []
      for _ in range(5): vals.append(round(g.f32(a), 5)); time.sleep(0.05)
      print(hex(a), "mod+" + hex(a - g.base) if g.base <= a < g.base + 0x2100000 else "", vals)
