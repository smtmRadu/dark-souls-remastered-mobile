"""Drive and inspect Dark Souls Remastered running natively on Windows (fast RE test bench).

  python pcgame.py key <name> [hold_s]   press a key in the game window (DirectInput scancodes)
  python pcgame.py shot [name]           screenshot of the game window
  python pcgame.py read                  print key game state values
Memory offsets: DSR 1.03.1 (same exe build as Dark-Souls-1-Overhaul; verified via AOB 0x1c77e50).
"""
import ctypes, ctypes.wintypes as wt, os, struct, sys, time

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)
EXE = "DarkSoulsRemastered.exe"

# --- static offsets from module base ---
WORLD_CHR_MAN = 0x1c77e50
MENU_MAN = 0x1c88d98
LOCK_TGT_MAN = 0x1c7a138
PAD_MAN = 0x1c6aea0
CAM_MAN = 0x1c6e188
FRPG_SYSTEM = 0x1b68e18

ctypes.windll.user32.SetProcessDPIAware()  # real pixel coords for window rects/screenshots
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi")


def find_pid():
    import subprocess
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {EXE}", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        p = line.replace('"', "").split(",")
        if p and p[0].lower() == EXE.lower():
            return int(p[1])
    return None


class Game:
    def __init__(self):
        self.pid = find_pid()
        if not self.pid:
            raise SystemExit("game not running")
        self.h = k32.OpenProcess(0x0010 | 0x0020 | 0x0008 | 0x0400, False, self.pid)  # VM_READ|VM_WRITE|VM_OPERATION|QUERY_INFO
        mods = (wt.HMODULE * 1024)()
        need = wt.DWORD()
        psapi.EnumProcessModulesEx(self.h, ctypes.byref(mods), ctypes.sizeof(mods), ctypes.byref(need), 0x03)
        self.base = mods[0]

    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return None
        return buf.raw[:got.value]

    def write(self, addr, data):
        got = ctypes.c_size_t()
        return k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(got))

    def u64(self, a):
        b = self.read(a, 8)
        return struct.unpack("<Q", b)[0] if b else 0

    def i32(self, a):
        b = self.read(a, 4)
        return struct.unpack("<i", b)[0] if b else None

    def f32(self, a):
        b = self.read(a, 4)
        return struct.unpack("<f", b)[0] if b else None

    def ptr(self, static_off, *chain):
        a = self.u64(self.base + static_off)
        for o in chain[:-1]:
            if not a:
                return 0
            a = self.u64(a + o)
        return a + chain[-1] if (a and chain) else a


# --- window + input ---
def hwnd():
    import win32gui
    found = []
    win32gui.EnumWindows(lambda h, _: found.append(h) if win32gui.GetWindowText(h).startswith("DARK SOULS") else None, None)
    return found[0] if found else None


def focus():
    import win32gui, win32con
    h = hwnd()
    if h:
        try:
            win32gui.ShowWindow(h, win32con.SW_RESTORE)
            import win32com.client
            win32com.client.Dispatch("WScript.Shell").SendKeys("%")
            win32gui.SetForegroundWindow(h)
        except Exception:
            pass
    return h


def key(name, hold=0.08):
    import pydirectinput
    pydirectinput.PAUSE = 0.02
    focus()
    time.sleep(0.15)
    pydirectinput.keyDown(name)
    time.sleep(hold)
    pydirectinput.keyUp(name)


def shot(name="pc"):
    import win32gui
    from PIL import ImageGrab
    h = hwnd()
    rect = win32gui.GetWindowRect(h) if h else None
    im = ImageGrab.grab(bbox=rect, all_screens=True)
    p = os.path.join(OUT, f"{name}.png")
    im.save(p)
    return p


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "key":
        key(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0.08)
    elif c == "shot":
        print(shot(sys.argv[2] if len(sys.argv) > 2 else "pc"))
    elif c == "read":
        g = Game()
        print("base", hex(g.base))
        print("main_menu_flag(menu_man+0x80)", g.i32(g.ptr(MENU_MAN, 0x80)))
        print("saved_chars_menu(menu_man+0xA4)", g.i32(g.ptr(MENU_MAN, 0xA4)))
        lt = g.u64(g.base + LOCK_TGT_MAN)
        print("lock bTargetLocked", g.read(lt + 0x1430, 2).hex() if lt else None)
        pc = g.ptr(WORLD_CHR_MAN, 0x68, 0x0)
        print("player ins", hex(pc), "hp", g.i32(pc + 0x3D8) if pc else None)
