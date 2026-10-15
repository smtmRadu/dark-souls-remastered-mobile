"""Drive the phone over adb: screenshots, OCR (Tesseract in WSL), taps by on-screen text.

Used for scripted tests of the Dark Souls APK (no human needed).
  python phone.py ocr                -> print words + boxes on screen
  python phone.py tap "Continue"     -> tap the word
  python phone.py enter_game         -> from app start to in-game (clears dialogs, picks Continue)
  python phone.py bench LABEL SECS   -> enter_game, then log FPS (DSRFPS logcat) + clocks
"""
import os, re, subprocess, sys, time

ADB = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe")
PKG = "com.remipelloux.gamenativecustom"
DISPLAY = "4630946564756762243"  # Flip6 inner screen (2640x1080 landscape)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)
ENV = dict(os.environ, MSYS_NO_PATHCONV="1")


def adb(*args, binary=False):
    r = subprocess.run([ADB, *args], capture_output=True, env=ENV)
    return r.stdout if binary else r.stdout.decode(errors="replace")


def shell(cmd):
    return adb("shell", cmd)


def screenshot(name="screen"):
    path = os.path.join(OUT, f"{name}.png")
    with open(path, "wb") as f:
        f.write(adb("exec-out", "screencap", "-d", DISPLAY, "-p", binary=True))
    return path


def wsl_path(p):
    p = os.path.abspath(p).replace("\\", "/")
    return "/mnt/" + p[0].lower() + p[2:]


def ocr(path=None, min_conf=40):
    """Return [(text, cx, cy, w, h)] for words on screen (white-on-dark game text -> inverted)."""
    from PIL import Image, ImageOps
    path = path or screenshot()
    inv = os.path.join(OUT, "ocr_in.png")
    ImageOps.invert(Image.open(path).convert("L")).save(inv)
    tsv = subprocess.run(["wsl.exe", "-d", "Ubuntu", "--", "tesseract", wsl_path(inv), "-", "--psm", "11", "tsv"],
                         capture_output=True, env=ENV).stdout.decode(errors="replace")
    words = []
    for line in tsv.splitlines()[1:]:
        c = line.split("\t")
        if len(c) < 12 or not c[11].strip():
            continue
        try:
            conf = float(c[10])
        except ValueError:
            continue
        if conf < min_conf:
            continue
        x, y, w, h = map(int, c[6:10])
        words.append((c[11].strip(), x + w // 2, y + h // 2, w, h))
    return words


def find(words, text):
    t = text.lower()
    return [w for w in words if w[0].lower().strip(".,:") == t]


def tap(x, y):
    shell(f"input tap {x} {y}")


def tap_text(text, words=None):
    words = words if words is not None else ocr()
    hit = find(words, text)
    if not hit:
        return False
    tap(hit[0][1], hit[0][2])
    return True


def fps_samples():
    out = adb("logcat", "-d", "-s", "DSRFPS:I")
    adb("logcat", "-c")
    return [float(m) for m in re.findall(r"DSRFPS\s*:\s*([0-9.]+)", out)]


def cold_start():
    shell(f"am force-stop {PKG}")
    time.sleep(2)
    adb("logcat", "-c")
    shell(f"monkey -p {PKG} -c android.intent.category.LAUNCHER 1")


def in_game():
    """Gameplay = FPS samples flowing and none of the menu/title words on screen."""
    words = {w[0].lower() for w in ocr()}
    return not ({"continue", "remastered", "ok", "press", "loading"} & words)


def enter_game(timeout=240):
    """From a cold start to gameplay: clear title/dialogs, pick Continue (never New Game)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        words = ocr()
        low = {w[0].lower() for w in words}
        if "ok" in low:
            tap_text("OK", words); time.sleep(3); continue
        if "continue" in low:
            tap_text("Continue", words); time.sleep(4)
            if "continue" not in {w[0].lower() for w in ocr()}:
                time.sleep(35)
                return True
            continue
        if {"press", "any", "button"} & low:
            tap(1320, 830); time.sleep(4); continue
        if "remastered" in low and {"game", "system", "quit"} & low:
            # menu wheel moved away from Continue: tap the item above the highlight until Continue shows
            g = find(words, "Game")
            tap(1320, (g[0][2] - 38) if g else 760); time.sleep(2); continue
        time.sleep(5)
    return False


def clocks():
    st = re.search(r"Thermal Status: (\d)", shell("dumpsys thermalservice | grep -m1 'Thermal Status'"))
    return {
        "status": int(st.group(1)) if st else -1,
        "max7": int(shell("cat /sys/devices/system/cpu/cpu7/cpufreq/scaling_max_freq").strip() or 0) // 1000,
        "gpu": int(shell("cat /sys/class/kgsl/kgsl-3d0/max_gpuclk").strip() or 0) // 1_000_000,
    }


def bench(label, secs=180):
    cold_start()
    time.sleep(70)
    ok = enter_game()
    log = open(os.path.join(OUT, f"bench_{label}.log"), "w")
    fps_samples()
    allv = []
    t0 = time.time()
    while time.time() - t0 < secs:
        time.sleep(15)
        v = fps_samples(); allv += v; c = clocks()
        line = f"{time.strftime('%H:%M:%S')} fps={v} {c}"
        print(line, file=log, flush=True)
    screenshot(f"bench_{label}")
    v = sorted(x for x in allv if x > 1)
    if not v:
        print(f"{label}: no samples (entered={ok})"); return
    s = f"{label}: entered={ok} N={len(v)} avg={sum(v)/len(v):.1f} p10={v[len(v)//10]:.1f} min={v[0]:.1f} >=28: {sum(x >= 28 for x in v)/len(v):.0%}"
    print(s); print(s, file=log)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "ocr":
        for w in ocr(): print(*w)
    elif cmd == "tap":
        print(tap_text(sys.argv[2]))
    elif cmd == "enter_game":
        print(enter_game())
    elif cmd == "bench":
        bench(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 180)
    elif cmd == "shot":
        print(screenshot(sys.argv[2] if len(sys.argv) > 2 else "screen"))
