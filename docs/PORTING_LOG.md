# Dark Souls Remastered → Android: porting log (2026-10-13)

Goal: one dedicated "Dark Souls" APK for the Galaxy Z Flip6 (Snapdragon 8 Gen 3, Adreno 750, Android 16) that feels like a native mobile game, with touch-first controls. Stable 30 FPS first, 60 later.
This file is the full record: what works, what failed, the mistakes, and how to repeat it for other games.

---

## 1. Current state (end of day 1)

| Area | State |
|---|---|
| Boot | ✅ App opens straight into the game (no login, no library). Splash says "Dark Souls". |
| Runtime | ✅ OpenNative fork, **legacy flavor (targetSdk 28)**, Wine `proton-9.0-x86_64`, **Box64 0.4.4** (bundled), PERFORMANCE preset, DXVK 2.4.1-gplasync, Turnip v26.2.0 R4, 1280x720 |
| Saves | ✅ PC save copied to the phone and loads (manual adb; in-app import/export not built yet) |
| Game state from memory | ✅ App reads the game's memory directly (`/proc/<pid>/mem`) → TITLE / LOADING / MENU / GAMEPLAY |
| Menus | ✅ No gamepad overlay. ✓ (A) / ✕ (B) buttons in the right black bar, swipe = d-pad steps, tap = mouse hover+click |
| Gameplay controls | ✅ v1 placeholder layout (stick, ATK, HVY, BLK, ROLL, PRY, 2H, USE, ITEM, d-pad, MENU), shown only in gameplay; drag on free area = camera; quick tap = R3 lock-on |
| Final control layout | ⏳ Being designed by the user in `design/final_wanted_controls.html` (rev 6, based on proposal #6 "Adaptive Hybrid"). Not implemented yet |
| FPS | ⚠️ 30 FPS (capped) on a cool phone; drops to ~14–20 FPS once the Flip6 throttles (see §4) |
| Tap-on-enemy lock-on | ⏳ All memory pieces found (enemy list, camera, lock handle); not wired yet |

Fork code: `local/opennative-src`, git branch `dsr`, **uncommitted** (29 files, +337/−30). Build: `./gradlew :app:assembleLegacyDebug` (JDK 17).

---

## 2. Timeline — what worked, what didn't

### 2.1 Setup
- Toolchain on the Legion: Temurin JDK 17+21, Android SDK/NDK 27.3, adb (winget), Ghidra 12.1.4 (`C:\Tools`), 7-Zip, MinGW-w64 + Tesseract + Wine 10 in WSL.
- Game copy: `local/game/` (from `C:\Games\Dark Souls\...`), Goldberg Steam emulator kept (user decision: no Steam for now). ReShade/DLSS files removed (Nvidia-only).
- APK base chosen: **OpenNative** (GPL-3 GameNative fork: Wine/Proton, FEX/ARM64EC, Box64, DXVK, Turnip, single-game launch intent). Rejected: stock Winlator (user wants no Winlator UI), DroidDeck (full SteamOS container, too heavy), GameNative (Steam-centric).

### 2.2 Getting it to boot (the hard part)
1. **Android storage crash.** OpenNative imported the game to `/storage/emulated/0/Android/data/...`. On launch, Android's **MediaProvider FUSE daemon aborted** (`NodeTracker::CheckTracked` in `pf_opendir`) while Wine scanned 6000 files → app killed, USB reset.
   **Fix:** game files in **app-internal storage** (`/data/user/0/<pkg>/CustomGames/`). Also faster I/O.
2. **Startup hang (100% CPU, no window)** with both FEX and Box64. Wrongly suspected: Steam emulator networking (Goldberg `disable_networking.txt`/`offline.txt` → no change), Box64 JIT (interpreter `BOX64_DYNAREC=0` hung identically).
   Proof it was Android-specific: same game folder ran fine under **Wine in WSL** on the PC.
   **Root cause (simpleperf on the spinning thread):** a SIGSEGV storm in `shim_segv_handler` (`libredirect-bionic-wx.so`). The "modern" flavor targets SDK 36 → Android **W^X** rules → DSR's anti-tamper writes into its own code pages → fault → resume → fault forever.
   **Fix:** build the **legacy flavor (targetSdk 28)**. Winlator worked for the user before because it also targets SDK 28.
3. **FEX/ARM64EC still loops** on the anti-tamper even with targetSdk 28 (time in `ill_handler`/`usr2_handler` + ntdll exception dispatch). **Box64 + x86_64 Proton boots** → title screen.

### 2.3 Performance
- Box64 COMPATIBILITY preset: 11 FPS in gameplay.
- **Box64 0.4.2 → 0.4.4 + PERFORMANCE preset + pin to fast cores (2–7)**: 30+ FPS, touching 60 on a cool phone.
- Thermal throttling (§4) then pulls it down to ~15 FPS after a minute on a heat-soaked phone.
- Added: 30 FPS cap default, display asks for 60 Hz in-game, game pinned to A720 cores 2–6 (no X4), `BOX64_DYNAREC_WEAKBARRIER=2`. Not yet measured on a cool phone.

### 2.4 Controls
- 6 layout proposals: `design/controls_proposals.html` (design agent). User picked #6 "Adaptive Hybrid" with changes → `design/final_wanted_controls.html` (designed in another chat).
- Game state without a mod DLL: Box64 maps the exe **1:1 at 0x140000000**, and the app (same uid) can read `/proc/<pid>/mem`. So the APK reads menu flags directly.
- Menu taps: DSR's title wheel ignores mouse clicks; gamepad navigation works in every menu → ✓/✕ buttons + swipe = d-pad.

### 2.5 Day 2 (2026-10-14): slow motion + CPU cost
- **Slow motion explained.** DSR advances game time in whole 1/60 s units per frame, capped at 2 units (1/30 s). Below 30 FPS the game runs at FPS/30 speed. Measured on the phone with `tools/timescale.sh` (in-game time `GameDataMan+0xA4` vs wall clock): 14.3 FPS → 0.46x. Confirmed on PC by throttling the process (NtSuspend duty cycle).
- **Box64 SMC cost.** simpleperf on the game: 12.5% in `cleanDBFromAddressRange`/`FindDynablockFromNativeAddress`/`MarkRangeDynablock`, called from `my_box64signalhandler → unprotectDB` (anti-tamper writes into code pages). DIRTY=0 also sends hot pages to the interpreter.
  - `BOX64_DYNAREC_DIRTY=1`: no gain. **`DIRTY=2` + `CALLRET=2` + `LOG=0` + `DYNAREC_MISSING=0`: +10% FPS at the same clock (14.3 → 15.8 @ 0.9 GHz), churn gone from the profile. Kept.**
  - `NOHOTPAGE=1` on top: worse (12.8). Reverted.
- **Bottleneck = game main thread (CPU).** GPU 33% busy at 231 MHz. DSR has only 4 graphics options (AA, MB, DoF, AO), all GPU post-process → no CPU win from graphics settings.
- **Heat.** Phone at 48–53 °C board while charging from the laptop → CPU capped 0.67–0.9 GHz → 12–16 FPS. Fast charging turned off for tests.
- **Loading screens.** In-game time stops on loading screens → `DsrGameState` reports LOADING while IGT is frozen > 300 ms → controls hidden until the area is loaded.
- **Clamp search (in progress).** Not a simple float constant: 1/30 float only in vector code; ring of per-task interval nodes (n × 1/60) found; hardware breakpoints on PC crash the game shortly after (anti-debug). Ghidra headless decompile of all `QueryPerformanceCounter` callers running.
- **App can READ but not WRITE game memory** (`/proc/pid/mem` O_RDWR and `process_vm_writev` both denied, SELinux). All writes must happen inside the game → **in-game agent**: `mod/dinput8/dinput8.c`, a `dinput8.dll` proxy (DSR imports DINPUT8), built with mingw in WSL, loaded via container env `WINEDLLOVERRIDES=dinput8=n,b`, logs to `A:\dsr_agent.log`. Works on the phone. This is also the channel for lock-on / UI mods later.
- `tools/memtool/memtool` (NDK, run via run-as): fast find/refs/read in game memory (2 s full scan).
- **Frame pacer RE:** `FrpgFlipper_*` classes (60FPS, 60FPS_NoSkip, 30FPS, 30FPS_NoSkip, 30FPS_DS1, _PAL, 140FPS); manager task (vtable 0x1412ea400) holds mode (+0x20, DSR = 4 = 60FPS) and the flipper (+0x28); factory switch at 0x140203f69. Swapping the live flipper to 30FPS: **no speed change**. Writing mode 0: the game resets it to 4 within 3 s. → the 1/30 s cap is elsewhere (time-step code still to find). IGT update: 0x140758a30 (`IGT += dt*1000`), dt arrives from task method 0x14024f6b0 (2nd arg), vtable in .data 0x141a29448 (obfuscated).
- **SOLVED: 1x speed (2026-10-14 19:25).** Guard-page stack trace from the agent (VEH + PAGE_GUARD on the IGT page, no debugger) showed the logic step is a **fixed tick of 1/60 s** (`.rdata` 0x1412ccc78, loaded once per frame at 0x14015cec9, passed to every system); the main loop (WinMain 0x140137f30 → frame fn 0x14015ce90) runs ticks, and the FrpgFlipper pacer allows at most 2 ticks per rendered frame → below 30 FPS the game can't reach 60 ticks/s. **Fix in the agent: tick = 1/30 (original DS1 / Switch rate) + 30FPS pacer** → 1 tick per frame at 30 FPS (half the logic CPU), 2 ticks per frame below → real-time speed down to 15 FPS. Measured on the throttled phone: **14.6 FPS, timescale 1.04** (was 0.46). Gameplay correctness at 30 Hz logic: to be checked by the user.
- Mod lead: Nexus "DS1 FPS Unlock – Remastered (DX11)" (id 1484) claims real-time speed when FPS dips (not checked: Nexus needs login).
- **Fixed tick was not enough (20:20).** At ~28–30 FPS the 1/30 tick gave **1.26–1.44×** (the game runs 2 ticks on some frames; the flipper only switches render-skip, logged through a wrapped vtable). **Speed governor** in the agent: every 0.5 s ticks = ΔIGT / (int)(tick·1000), tick := real time / ticks (smoothed, clamp 1/60…1/10). Measured **0.99–1.00×** at 17 and 28 FPS.
- **Box64 perf map unusable on Android:** `BOX64_DYNAREC_PERFMAP` writes a hardcoded `/tmp/perf-<pid>.map` (no /tmp on Android) → nothing. **In-game sampling profiler instead:** the agent suspends the main thread (~400 Hz), reads the x86 context and unwinds with `RtlVirtualUnwind`; `tools/profile.sh` + `tools/stackprof.py` give self/inclusive time per game function. Works on the phone and the PC, no debugger.
- **Input polling was ~23% of the main thread:** GetAsyncKeyState × 236 keys per frame (13%, each a wineserver round trip), DirectInput Poll/GetDeviceState on 8 devices per frame (~9%), SystemParametersInfo(SPI_SETMOUSE) per frame. Agent: IAT hooks + DirectInput vtable hooks serve cached state (keys 20 Hz, devices 100 Hz on agent threads). Same spot: **17.2 → 28.1 FPS, 125M → 72M cycles/frame**, controls verified (stick moves the player).
- **Frame skip found (21:30).** One call of the per-frame function = one logic tick. The 30FPS flipper skips rendering after slow frames, so the game ran 45 ticks/s for 30 rendered frames. **NoSkip flipper (0x1412ea790) + governor:** 30 ticks/s at 30 FPS, 0.98× on the IGT probe (IGT truncates tick ms, true speed 1.00), −5% CPU at the same FPS.
- **DirectInput cache crash (fixed).** Wine's A devices forward to the shared W vtable; my hooks called the wrong original for objects outside the cache → startup crash ~1 in 3. Fix: originals stored per vtable, looked up via the object's vtable; Release hooked so the poller drops freed devices. 4/4 + 2/2 clean boots after.
- **Box64 A/B (cycles per 10 s at the 30 FPS cap):** base 20.8G; `SAFEFLAGS=0` 18.8G (−10%, 96% of samples ≥28 FPS).
- Next CPU targets from the profile: character update 23% (chr dispatcher 0x14036f610), main thread waiting on worker jobs 16%.

---

### 2.6 Day 3 (2026-10-15): one APK, no startup popups, native-feeling HUD
- **CPU A/B** (same spot, PC save): character LOD 4/8/25 + event pool = 66.6M cycles/frame vs 75.5M stock (−12%), both locked 30 FPS. Kept on. One single-flag run never reached gameplay; the full build then passed boottest 4/4.
- **Startup popups** were the game's, not the app's (found by screenshotting every 3 s of a cold start):
  1. "Last time, the game may not have been closed using Quit Game…": Android kills the exe. Found by diffing decrypted saves (`tools/sl2.py`: BND4, 11 entries, MD5 + IV + AES-128-CBC, public DSR key): system entry 10, byte 0x1068 = 1 after a kill. The app clears it before launch.
  2. "Game will start in offline mode.": stays even with Network > Launch setting = Start Offline. The app answers the first general dialog of a run (MenuMan +0x74 = 1) with one A press. Start = 1 tap to the main menu.
- **Quick taps were missed** (Start, menu ✕): the game samples input once per frame. Every press now lasts ≥ 80 ms.
- **Menu swipes undone by hover**: the pointer left over a row made the game snap the selection back each frame. No hover on touch-down; park the pointer at (0,0) after a tap-click. Row taps then work (select + open).
- **Interaction prompt from memory**: MenuMan+0x828 = Event_text_ id of the map-action prompt (−1 none; 10010103 = "Pick up item"), +0x81c = item-get popup item id. Found by decompiling FrpgMenuDlgMapAction (RTTI name → vtable → Update) and confirmed by dropping an item and walking onto it.
- **Equipment from memory**: PlayerGameData+0x324 holds item ids directly (Overhaul's PlayerInsStruct.h layout matches DSR). Mistake: a dump started at +0x390 was read as +0x3a0 → inventory pointer looked like +0x3e8; the app read 0. Always label dumps from the actual start address.
- **Game assets without shipping them**: `tools/extract_assets.py` (+ `tools/fromsoft/`: DCX, BND3, TPF, PARAM, paramdef, FMG, DRB) cuts 921 icons from the menu atlases using the remastered `menu.drb.dcx` sprite layout (`EquIcon_<iconId>`), and writes items/prompts json. Run on the user's own copy → `<game>/dsr_assets/`.
- **Hiding stock HUD parts**: patch the dialog class vtable slot 16 (Update) and clear bit 1 of `obj+0x28` for each object in `dlg+0x18` (count `+0x20`) after the original update (Overhaul's UIFeatures trick). Works for FeShortcut (slot block) and MapAction (prompt box). FrpgMenuDlgObjItemSelect (quick item name) ignores it: it owns sub-elements.
- **No black bars**: DSR is natively Hor+ with a corner-anchored HUD; the bars came only from the app's 1280x720 X screen. The app sizes the X screen to the display ratio (~1.1x 720p pixels: Flip6 1584x648, S23 Ultra 1544x720); the agent pins the display option to borderless at the desktop size and strips the window caption (IAT hooks from DllMain). +5% CPU per frame, still 30 FPS. Research: docs/ui/ASPECT_RATIO.md.
- **800x600 in the corner after a restart**: the game reads its display mode from `AppData/Local/FromSoftware/NBGI/DarkSouls/DarkSouls.ini` at boot (not the save). After a borderless 1584x648 run it fell back to fullscreen 800x600, rewrote the ini, and the agent's one-time pin came too late: the picture filled only the top-left. The app now writes `WindowMode=2` + Width/Height = screen size into the ini before every launch (tested from a broken ini).
- **Moving stock HUD parts** (`tools/patch_menu.py`): positions live in `menu/menu.drb.dcx` (DRB shape params: rect, scaling origin, scaling type 1 = top-left anchor, 2 = bottom-left, 3 = bottom-right, 5/6/7 = centre). HUD root dialog `F20-00`. Souls box = child dialog `soul_param` (was bottom-right, now top-left above the HP bar; souls gained shown to its right). Quick item name = `text_item_name` (now under the app's Estus slot, left edges aligned). The text alignment field (+0x14) did not centre this text. The DCX is re-packed with the original header + zlib level 9.
- **Main menu in one row**: FrpgMenuDlgTitle (vt 0x1413b5b10, Update = slot 16 = 0x140693280) fills 5 text slots `button3_0..button7_0` from an entry vector (+0x210, 12 bytes {text id, action, ?}; +0x23c scroll top, +0x234 highlighted slot, +0x244 count). The vector is rebuilt from a static 10-entry table at 0x141a32250; with > 5 entries the game scrolls a 4-entry window, with <= 5 it shows entry i in slot i. Offline the "Log In" entry made 6. The agent sets its action 5 -> 7 (always filtered), and patch_menu.py moves the 5 slots + their `cursor<i>_0` highlight rects into one row with font 11. The title logo is drawn by code, not by the DRB.
- **DRB text params**: byte +0x1c = font (6 menu, 7/8 lists, 10/11 titles, 12 big), byte +0x1e = alignment (1 right, 2 centre-x, 8 centre-y). +0x14 looked like alignment but is not.
- **Game-style touch controls**: `extract_assets.py` also cuts the stock HUD pieces (slot background, bronze bracket, icon plate, parchment) into `dsr_assets/ui/`; the app draws slots, circles, pills and the stick with them, and falls back to the flat look without them.
- **Touch camera**: ChrExFollowCam = `[[[0x141c7a488]+0x60]+0x60]` (vt 0x1412eefd8): +0x144 yaw, +0x140/+0x150 pitch, +0x1fc..+0x228 speed pairs (yaw base 120 deg/s, max 260 deg/s, interpolated by |stick|). Writing yaw directly does not hold: the update (0x14023704a) recomputes it. So the app sends a smoothed finger velocity on the right stick (past the dead zone, eased out) and the agent scales the speed fields x1.5. Shared-file mapping between the app and Wine works (MapViewOfFile on a file the app also maps) but was not needed in the end.
- **Mistake: thread check.** The agent assumed GetDeviceState runs on the game thread; it runs on an input thread, so tap-to-lock silently never applied. Per-frame game-thread work now hangs off a dialog Update vtable hook.
- **Two-handing state**: player ChrIns+0xb20 (1 one-hand, 3 right 2H, 2 left 2H), found by diffing ChrIns across 2H toggles (PlayerGameData does not change).
- **Title**: "PRESS ANY BUTTON" is FMG text on the heap (2 FMGs, 8 copies incl. languages): the agent rewrites it in place (ReadProcessMemory/WriteProcessMemory on itself, safe against freed regions). Title dialog +0x254/+0x255 = 1/1 when the main-menu entries show.
- **Title logo higher**: the title logos are full-screen 1920x1080 images drawn centred at the .rdata constant {960, 540} (0x1412f6150), read only by the two title draw functions (0x14025bcf0, 0x14025c2a0; checked every RIP-relative reference). The agent sets y = 450. The DRB Title dialogs are not used for it.
- **Mistake: direct memory scans in the agent.** swap_flipper read every private RW region directly, every 1 s until found and every 10 s after. If the game freed a region between VirtualQuery and the read, the whole game crashed. Symptom: boots dying a few seconds into loading (~1 in 4), the agent log ending at the scan. Rule: scan with ReadProcessMemory on our own process (fails cleanly), write with WriteProcessMemory.
- **Sharper picture**: render budget 2.0x 720p (Flip6 2112x864): still a locked 30 FPS moving + turning, GPU 34% -> 53%. The CPU (Box64), not the GPU, limits the frame rate, so pixels are cheap. **WRONG, reverted (see next bullet).**
- **MISTAKE: 2.0x render cooked the phone (2026-10-15).** The 53 % GPU above was a short cool test. In real play GPU went
  85-100 %, the phone reached ~70 °C, and heat throttling (CPU down to ~0.9 GHz) brought the frame drops. Pixels are NOT
  cheap: heat is the real budget on a phone. Fix: `DsrLauncher.RENDER_BUDGET` 2.0 -> 1.2 (1584x648 on the Flip6), the
  game's GPU post effects off at every start (`[DisplaySettingFilter]` Blur / Antialiasing / DOF / AmbientOcclusion = 0
  in DarkSouls.ini, `writeDisplayIni`), and `DsrGpuGovernor` steps the render size per session to keep gameplay GPU
  <= 50 % (user target). **Do not raise the render budget or turn the post effects back on without a 15-min heat test
  (GPU %, CPU/GPU temp, FPS over time).** First check at 1.2: GPU 58 % at 58 °C (governor steps down next start).
  Note: Adreno busy % is relative to the current clock, so it reads high at low clocks; watch temperature too.
- **Tap-to-lock** (docs/LOCKON.md): the app projects LockTgtMan's candidate list with ChrCam and writes `dsr_lock.txt`; the agent moves the 0x20 target flag + sets the lock request on the main thread (inside the GetDeviceState hook). Implemented, not yet tested near enemies.
- **Tooling gotchas**: SELinux blocks `sendevent` for the shell even with the input group; adb taps are near-instant (use ≥ 80 ms presses); short adb stick swipes (< 1 s) don't move the character; with `MSYS_NO_PATHCONV=1`, `adb push` needs a Windows path.

## 3. Mistakes (and the rule learned)

| Mistake | Cost | Rule |
|---|---|---|
| Assumed this machine was the Pavilion from the `radup` home path | confusion | Check the hardware model, not the home path |
| `adb tcpip 5555` on a phone with **no Wi-Fi** | phone unreachable until the user toggled USB debugging | Only switch adb to TCP after confirming a Wi-Fi IP |
| Blind adb taps in the DSR menu wheel (it scrolled to "New Game") | slow testing, risk to the save | Navigate menus with gamepad (✓/✕, d-pad); read state from memory, not screenshots |
| `toybox dd skip=` to read `/proc/pid/mem` | false "I/O error" | toybox dd reads from 0 to skip; use `xxd -s` or a seeking reader |
| DsrGameState checked only the first line of `/proc/pid/maps` | attach never worked | Search all lines for the `140000000-` mapping |
| Loaded the controls profile from the asset stream | zero elements (they load from the profiles dir) | Copy `controls-6.icp` to the profiles dir, then load from file |
| A second XServer code path re-hid the overlay | controls never shown | DSR mode skips all generic show/hide paths |
| Ran the game on the PC with the user's real save | PC save autosaved | Restored from `local/saves_backup/`; next time use a copy / separate profile |
| Performance tests on a heat-soaked phone (3 h, on laptop USB) | misleading 14–16 FPS numbers | Benchmark only from a cool start; log real thermal zones |
| Changed the user's Samsung performance profile without asking | — | Ask before changing phone settings (later user asked for max) |
| Static RE through Arxan-obfuscated vtables for hours | slow | Trace at runtime from inside the game (agent VEH + guard page → call stack) first |
| Wrote a control layout while the user was designing it elsewhere | duplicate work | Layout lives in one profile file; wait for the user's spec |
| Fable research agent stalled (no output) | no research yet | Re-run it with a smaller scope (day 2 rerun worked: 5 focused questions) |
| Started a bench with `&` inside a background command, then a second one | two benches fought over the phone, mixed data | One bench at a time; never `&` inside `run_in_background` |
| Declared 1× from one measurement at 15 FPS | 1.26–1.44× at 30 FPS went unnoticed | Measure the timescale across the FPS range (cool and hot phone), not at one point |
| PAGE_GUARD on a heap page (pacer object) | game crashed | Guard only pages that only game code touches; to watch a C++ object, wrap its vtable instead |
| Hardware breakpoint (debugger attach) on the PC game | game killed by anti-debug; autosave risk | Back up the save first, restore after every PC session |

---

## 4. Thermal facts (Flip6)
- The Flip6 throttles on **board/skin and battery temperature**, not SoC temperature. Readable sensors: `/sys/class/thermal/thermal_zone*/` types `xo-therm` (board ≈ skin), `battery`, `cpu-1-*`, `gpuss-0`.
- At `xo-therm` ≈ 50 °C / battery ≈ 43 °C: CPU capped to **0.9 GHz** (from 3.4), GPU to 310–500 MHz → ~14.5 FPS. SoC itself only 54 °C.
- `dumpsys thermalservice` values are cached (not live). `cmd thermalservice override-status` changes the reported status but **not the clocks** (vendor engine, needs root).
- Laptop USB can't keep up: the battery drains while charging circuitry still heats it.
- Samsung settings: `settings get global restricted_device_performance` (`1, 1` = Light profile, `0, 0` = max). Currently `0, 0` (user asked for max).
- 2026-10-14: fast charging turned OFF for testing (`settings put system adaptive_fast_charging 0`; was 1). Restore later with value 1.

---

## 5. Reverse engineering (exe 1.03.1 = Dark-Souls-1-Overhaul build)
Full notes: `re/RE_NOTES.md`. Highlights:
- Static pointers (base 0x140000000): WorldChrMan 0x1c77e50 (AOB-verified), MenuMan 0x1c88d98, LockTgtManImp 0x1c7a138, PadMan 0x1c6aea0, CamMan 0x1c6e188.
- **MenuMan+0x50** = active menu id (0 = gameplay, 8 = menu bar, 2 = inventory); **MenuMan+0x80** = title menu.
- Characters: per-map arrays in WorldChrMan at `0x7b8 + i*0xE8` (count at −8, entries stride 0x38, ChrIns* at +0). Vtables: PlayerIns 0x1413251f0, EnemyIns 0x141322e68. HP at ChrIns+0x3E8/+0x3EC, handle at +0x8, position `[[c+0x68]+0x28]+0x10`.
- Camera: `[[base+0x1c6e188]+0x10]`: rotation rows at +0x10, position +0x40, vertical FOV +0x50 (0.75 rad). Projection checked against the player (screen centre).
- Lock-on: LockTgtManImp+0x1430/0x1431 flags; target handle in the player's PadManipulator (`LockonTargetHandle`).

---

## 6. Reusable recipe for other PC games
1. Base on OpenNative, **legacy flavor (targetSdk 28)** if the game has anti-tamper / self-modifying code.
2. Game files in **app-internal storage**, never shared storage.
3. Try Box64 (x86_64 Proton) and FEX (ARM64EC); profile a hang with `simpleperf record --app <pkg> -p <pid>`.
4. Validate on PC with Wine in WSL to split "Wine/game" from "Android" problems.
5. Box64 PERFORMANCE preset + newest Box64 + pin to performance cores; cap FPS; lower display refresh.
6. Read game state from `/proc/<pid>/mem` (Box64 maps PE images 1:1) → context-aware touch layer without a DLL.
7. Benchmark only from a cool phone; log `xo-therm`/battery.

---

## 7. Next steps
1. **Re-measure FPS on a cool phone** with the new settings (60 Hz, A720 cores, weak barriers): `tools/bench.sh LABEL 300`.
2. **Try FEX in full x86-64 mode** (DroidDeck reportedly runs DSR at a stable 60 FPS with FEX on SD 8 Gen 2/3). Could cut CPU (and heat) a lot.
3. Re-run the in-game optimization research (Fable agent stalled): graphics settings that cut CPU, engine knobs, Box64/DXVK tuning.
4. Implement the user's final layout from `design/final_wanted_controls.html`.
5. Tap-on-enemy lock-on (projection + LockonTargetHandle write from the app).
6. In-app save import/export, first-run import, own package id + icon.
7. **Functional Load Game:** the in-game Load Game menu lists and loads any save file (all characters/slots, imported saves).

## 8. Where things are
| Path | What |
|---|---|
| `local/opennative-src/` (branch `dsr`) | APK source. Key new files: `app/gamenative/dsr/DsrLauncher.kt`, `DsrGameState.kt`, `assets/inputcontrols/profiles/controls-6.icp`, `assets/box86_64/box64-0.4.4-bionic.tzst`; DSR logic in `InputControlsView.java` |
| `.track/` | Roadmap, policy (all decisions dated), milestone notes incl. `v0.2.0/opennative-code-map.md` |
| `re/` | RE notes + cloned DSR-Gadget and Dark-Souls-1-Overhaul |
| `tools/` | `bench.sh` (auto benchmark), `phone.py` (OCR driver, superseded), `pcgame.py` (PC memory reader/driver), RE scripts |
| `design/` | Control proposals + final wanted controls |
| `local/saves_backup/` | PC save backups (original + after-test copy) |

## 2026-10-15 — MISTAKE: menu HUD hiding saved HUD OFF into the save
- The agent forces the HUD option off in menus and restores it during the System "decide" step (state[0x2a] == 3).
- That step lasts only a frame or two. The 50 ms agent loop missed it, so Options opened showing HUD OFF.
- Back on Options reverts to the value read at open: the game stored OFF for real. Gameplay lost the HP bars.
- Fix: `menu_hud` runs on its own 2 ms thread (`hud.c`); transitions are logged (`menuhud: forced off / back to`).
- Rule: any option forced by the agent must be restored before the page that shows it opens. Test with Options → Back.
- 20:05 follow-up: the repair (HUD ON + OK at 19:44) was lost: the game was killed before it wrote the save. The next session started with HUD 0 and the restore kept putting 0 back. Now `menu_hud` locks the option to 1 outside menus (no saved value at all).

## 2026-10-15 — Offline notice removed (handler pointers, not code)
- "Game will start in offline mode." = text id 0xc545 (`System_message_win32_` FMG). Two title state handlers show it through the general dialog (0x140686bc0 init, 0x140686c20 set text, 0x140686f30 show).
- 0x14028a720 → state 0xc; the 0xc handler (0x14028a810) moves on at once when no general dialog is open.
- 0x140804c60 → state 0x40; the 0x40 handler (0x140804cc2) waits for a button, then sets +0xc0 = 1 and state 0xa.
- How found: FMG text → `mov edx, 0xc545` sites → handler registration code (0x140013d70, 0x140037548) that stores each handler in .data (0x141c715c8, 0x141c8b278).
- **MISTAKE: a .text patch (NOP the show call) killed the game 2 s after start** (20:56, anti-tamper). Never write .text.
- Fix: the agent swaps the two .data pointers for its own functions once static init has filled them (`title.c patch_offline_notice`): site 1 → state 0xc with no dialog, site 2 → the OK result. Flag file `dsr_offlinenotice` keeps the notice.
- The app's A-press fallback acts only on the bare title, so it never confirms a real question (Quit Game).
