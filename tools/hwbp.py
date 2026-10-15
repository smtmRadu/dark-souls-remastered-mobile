"""hwbp.py ADDR [w|rw] [hits]: hardware breakpoint on a PC DSR address; prints the instructions that access it.
Attaches as a debugger for a moment (Win32 debug API), sets DR0 on every thread, then detaches."""
import ctypes, ctypes.wintypes as wt, sys, struct, collections, time
from pcgame import find_pid
k = ctypes.WinDLL("kernel32", use_last_error=True)
addr = int(sys.argv[1], 16); mode = sys.argv[2] if len(sys.argv) > 2 else "w"; want = int(sys.argv[3]) if len(sys.argv) > 3 else 40
pid = find_pid()
TH32CS_SNAPTHREAD = 4
class TE(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD), ("th32OwnerProcessID", wt.DWORD),
                ("tpBasePri", wt.LONG), ("tpDeltaPri", wt.LONG), ("dwFlags", wt.DWORD)]
def threads():
    s = k.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0); te = TE(); te.dwSize = ctypes.sizeof(te); out = []
    ok = k.Thread32First(s, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid: out.append(te.th32ThreadID)
        ok = k.Thread32Next(s, ctypes.byref(te))
    k.CloseHandle(s); return out
raw = ctypes.create_string_buffer(1232 + 16); base = (ctypes.addressof(raw) + 15) & ~15
def setdr(tid, on):
    h = k.OpenThread(0x0002 | 0x0008 | 0x0010 | 0x0040, False, tid)  # SUSPEND|GET|SET ctx|QUERY
    if not h: return
    k.SuspendThread(h)
    ctypes.memset(base, 0, 1232); ctypes.c_uint32.from_address(base + 0x30).value = 0x00100010
    if k.GetThreadContext(h, ctypes.c_void_p(base)):
        rw = 0b01 if mode == "w" else 0b11
        ctypes.c_uint64.from_address(base + 0x48).value = addr if on else 0
        ctypes.c_uint64.from_address(base + 0x70).value = (1 | (rw << 16) | (0b11 << 18)) if on else 0
        k.SetThreadContext(h, ctypes.c_void_p(base))
    k.ResumeThread(h); k.CloseHandle(h)
if not k.DebugActiveProcess(pid): sys.exit(f"attach failed {ctypes.get_last_error()}")
k.DebugSetProcessKillOnExit(False)
ev = ctypes.create_string_buffer(176); hits = collections.Counter(); armed = False; t0 = time.time()
while sum(hits.values()) < want and time.time() - t0 < 15:
    if not k.WaitForDebugEvent(ev, 200):
        continue
    code, p, t = struct.unpack_from("<III", ev, 0); cont = 0x00010002  # DBG_CONTINUE
    if code == 1:  # EXCEPTION
        exc, = struct.unpack_from("<I", ev, 16); ea, = struct.unpack_from("<Q", ev, 16 + 16)
        if exc == 0x80000004: hits[ea] += 1
        elif exc == 0x80000003 and not armed: pass  # attach breakpoint
        else: cont = 0x80010001  # DBG_EXCEPTION_NOT_HANDLED
    if not armed:
        for tid in threads(): setdr(tid, True)
        armed = True
    k.ContinueDebugEvent(p, t, cont)
for tid in threads(): setdr(tid, False)
# drain pending events then detach
for _ in range(50):
    if not k.WaitForDebugEvent(ev, 50): break
    code, p, t = struct.unpack_from("<III", ev, 0); k.ContinueDebugEvent(p, t, 0x00010002)
k.DebugActiveProcessStop(pid)
for a, n in hits.most_common(): print(hex(a), n)   # address AFTER the accessing instruction
