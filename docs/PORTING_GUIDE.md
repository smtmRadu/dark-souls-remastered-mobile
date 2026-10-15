# Porting a PC game to a dedicated Android APK

A reusable recipe, learned on Dark Souls Remastered (DSR) → Galaxy Z Flip6 (Snapdragon 8 Gen 3).
Game-specific details: `docs/dsr/`. Full history with every failure: `docs/PORTING_LOG.md`.

Follow the phases in order. Each phase ends with a check you can measure.

---

## Phase 1 — Base APK

1. Fork **OpenNative** (GPL-3 GameNative fork: Wine/Proton, Box64, FEX/ARM64EC, DXVK, Turnip, single-game launch intent).
2. Build the **legacy flavor (targetSdk 28)**. The modern flavor (SDK 36) enforces W^X. Games with anti-tamper or self-modifying code then fault forever in `shim_segv_handler`.
3. Add a build flag (`DSR_MODE` here) for all single-game changes: direct launch, no login, no library, own name.
4. Put the game in **app-internal storage** (`/data/user/0/<pkg>/...`). Shared storage (`/storage/emulated/0`) crashes the MediaProvider FUSE daemon when Wine scans thousands of files.

**Check:** the app opens straight into the game's title screen.

## Phase 2 — Make it boot

- Try both emulators: **Box64 + x86_64 Proton** and **FEX/ARM64EC**. On DSR, FEX looped in exception handling on the anti-tamper; Box64 booted.
- A hang with 100% CPU and no window: profile it, don't guess.
  `setprop security.perf_harden 0`, then `simpleperf record --app <pkg> -p <pid> -g`. The DSR hang was a SIGSEGV storm (W^X), visible in one profile.
- Split "Android problem" from "Wine/game problem": run the same game folder under Wine in WSL on the PC.

**Check:** title screen on the phone, logs clean.

## Phase 3 — Measure correctly

Build these probes first. They make every later test fast and objective.

| Probe | What | DSR file |
|---|---|---|
| FPS log | app logs the frame rate every 2 s | `FrameRating.java` (`DSRFPS`) |
| Game state | phase TITLE / LOADING / MENU / GAMEPLAY from game memory | `DsrGameState.kt` |
| Timescale | in-game time advance ÷ wall-clock time (1.00 = real speed) | `tools/timescale.sh` |
| Speed check | distance walked in 4 s of real time | `tools/speedcheck.sh` |
| Bench | cold start → enter gameplay → move + turn camera → FPS, clocks, temps, timescale, profile | `tools/bench.sh` |

Rules:
- **Benchmark from a cool phone.** Log `xo-therm` (board/skin) and `battery` from `/sys/class/thermal`. The Flip6 throttles on those, not on the SoC temperature. A heat-soaked phone gives misleading numbers.
- Charging from a laptop heats the battery. Turn off fast charging during tests, or test unplugged over Wi-Fi adb.
- Move the character during benchmarks. A static scene is not representative.
- Run one benchmark at a time.

## Phase 4 — Read game memory from the app

- Box64 maps the PE image 1:1 (DSR: `0x140000000`). The app runs as the same uid, so it can **read** `/proc/<pid>/mem`. Find the pid by cmdline + a `maps` line starting with the image base.
- Find static pointers on the PC first: AOB patterns from community tools (DSR-Gadget, SoulSplitter, Cheat Engine tables), then verify in memory.
- `tools/memtool` (NDK binary, run via `run-as`): fast find / refs / read. A full scan takes about 2 s.
- toybox `sh` arithmetic is 32-bit and toybox `dd skip=` fails on `/proc/pid/mem`. Use `xxd -s <hex>` or memtool.

## Phase 5 — Write game memory: the in-game agent

- The app **cannot write** game memory. `/proc/pid/mem` O_RDWR and `process_vm_writev` are denied by SELinux.
- Solution: a **proxy DLL** that the game loads itself. Pick a DLL the exe imports and that the game folder doesn't ship (DSR: `DINPUT8.dll`). Forward its exports to the system DLL and start an agent thread in `DllMain`.
- Build with mingw in WSL: `x86_64-w64-mingw32-gcc -O2 -shared -o dinput8.dll dinput8.c dinput8.def -static-libgcc`.
- Load it with the container env var `WINEDLLOVERRIDES=dinput8=n,b`. The app copies the DLL into the game folder on every start (`DsrLauncher.installAgent`).
- The agent logs to a file in the game folder. Read it with `run-as ... cat`.

## Phase 6 — Runtime tracing (beats static RE)

Static RE through obfuscated (Arxan) code is slow. Trace at runtime from inside the game:

- **Find a value:** scan memory while you change the game state (e.g. throttle the PC game with an `NtSuspendProcess` duty cycle; compare values at full speed and when slowed).
- **Find the code that touches it:** in the agent, add a vectored exception handler and put a one-shot `PAGE_GUARD` on the value's page. The handler logs `Rip`, registers and return addresses on the stack. Re-arm from the agent thread. No debugger is attached, so anti-debug doesn't trigger.
- Don't attach a debugger to games with anti-debug. DSR killed itself a few seconds after hardware breakpoints.
- Static helpers: `re/xref.py` (callers, function bounds from `.pdata`) and a Ghidra **no-analysis** headless decompile of chosen functions (minutes instead of hours; full auto-analysis is single-threaded and slow).
- RTTI type names (`.?AV...`) give class names and vtables. That's how DSR's frame pacer (`FrpgFlipper_*`) was found.

## Phase 7 — Performance

Order: measure → remove waste → reduce work → reduce quality (last resort).

1. **Emulator waste.** Profile the game process. In DSR, 12% went to Box64 code-cache invalidation from anti-tamper writes. `BOX64_DYNAREC_DIRTY=2` fixed it (+10% FPS). Test one flag at a time; some flags make it worse (`NOHOTPAGE=1`: −20%).
2. **Find the real bottleneck.** `top -H` per thread, and GPU busy % (`/sys/class/kgsl/kgsl-3d0/gpu_busy_percentage`). DSR: the game's main thread at 0.9 GHz; the GPU was 33% busy. So graphics settings could not help.
3. **Game speed vs frame rate.** Many games run fixed logic ticks and drop ticks when slow → slow motion. Measure the timescale **at several frame rates**. DSR: fixed 1/60 s ticks, max 2 per frame → speed = FPS/30 below 30 FPS. A fixed 1/30 tick was right at 15 FPS but 1.3× at 30 FPS. Final fix: a **closed-loop governor** in the agent: count ticks per second (from a per-tick counter such as in-game time) and set tick length = real time / ticks.
2b. **Find the CPU hogs with an in-game sampler** (agent suspends the main thread, `GetThreadContext` + `RtlVirtualUnwind`). Box64's perf map needs /tmp, which Android lacks. Look first at **syscall-heavy calls per frame** (input polling, window queries): each one is a wineserver round trip under Wine. DSR: 23% of the main thread was input polling; caching it in the agent gave +60% FPS.
4. **Heat.** Cap the frame rate (30). Ask the display for 60 Hz instead of 120 Hz. Pin the game to efficient cores. Reduce graphics only if the GPU is the bottleneck.

## Phase 8 — Native-feeling controls

- Draw touch controls only in gameplay (phase from memory); hide them in menus, loading screens and cutscenes.
- DSR's in-game time stops on loading screens: "no time advance for 300 ms" = still loading.
- Menus: gamepad buttons (✓/✕) + swipe = d-pad work everywhere. Mouse clicks don't work in every game menu.
- Camera: drag on the free screen area. Lock-on: tap the enemy (project enemy positions with the camera matrix; write the target through the agent).

## Phase 9 — Release

- Publish only your code, patches, offsets and docs. Never game files, executables, saves or Steam-emulator files.
- Users bring their own copy. Document the exact game version (exe hash) your offsets need.
