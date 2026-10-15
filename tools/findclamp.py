"""Find DSR's clamped frame step on PC: floats that are 1/60 at full speed and only ever 1/60 or 2/60 while throttled."""
import time, ctypes, threading, math
from finddt import g, regions
nt = ctypes.WinDLL("ntdll"); h = ctypes.windll.kernel32.OpenProcess(0x0800, False, g.pid)
c = {}
for b, n in regions():
    d = g.read(b, n)
    if not d or len(d) % 4: continue
    for i, v in enumerate(memoryview(d).cast('f')):
        if 0.0165 <= v <= 0.0168: c[b + 4 * i] = v
stop = False
def duty():
    while not stop: nt.NtSuspendProcess(h); time.sleep(0.06); nt.NtResumeProcess(h); time.sleep(0.01)
th = threading.Thread(target=duty); th.start(); time.sleep(1.5)
seen = {a: [] for a in c}
for k in range(40):
    for a in list(seen):
        x = g.f32(a)
        if x is None or math.isnan(x) or math.isinf(x): seen.pop(a); continue
        seen[a].append(x)
    time.sleep(0.03)
stop = True; th.join(); nt.NtResumeProcess(h)
q = lambda x: abs(x * 60 - round(x * 60)) < 0.02 and 0 < x < 1
for a, v in seen.items():
    if v and all(q(x) for x in v) and 0.03 < max(v) < 0.034 and v.count(max(v)) > 3:
        print("%x" % a, sorted(set(round(x, 4) for x in v)))
