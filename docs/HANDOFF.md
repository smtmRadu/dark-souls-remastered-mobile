# Handoff — 2026-10-14 ~22:00

State of the Dark Souls Remastered Android port and the next steps for the agent that continues.
Read first: `.track/POLICY.md`, `.track/v0.2.0.md`, `docs/PORTING_LOG.md` §2.5, `re/RE_NOTES.md`, `docs/ui/UI_RE.md`, `docs/CONTROLS.md`.

## Rules (from the user)
- **Private use only.** Play offline. Commit only when asked: branch `dsr` in `opennative-src/` is uncommitted.
- **Ask before:**
  - git push;
  - destructive operations;
  - phone settings changes beyond the agreed ones.
- **Phone:** only one session uses the phone. Run one benchmark at a time. Move the character in tests.
- **PC:**
  - Never send keyboard or mouse input to the PC.
  - Never attach a debugger to the PC game (anti-debug).
  - Back up the PC save before any PC game run.
- **Work style:** be concise. Write all findings into the docs: a GitHub release and another game port come later.

## Results so far (all measured on the phone, Galaxy Z Flip6)
| Item | State |
|---|---|
| Game speed | **1.00×** at any FPS. The agent's speed governor sets tick length = real time ÷ ticks every 0.5 s. `tools/timescale.sh` shows 0.98: IGT truncates ms per tick. |
| Frame pacer | Agent swaps FrpgFlipper_60FPS → **30FPS_NoSkip** (0x1412ea790): 1 logic tick per rendered frame. The skip pacer ran 45 ticks/s for 30 renders. |
| Input cost | Agent caches GetAsyncKeyState (20 Hz), SystemParametersInfo mouse, DirectInput Poll/GetDeviceState (100 Hz poller thread). Heavy spot: 17 → 28 FPS. |
| Box64 | DIRTY=2, CALLRET=2, WEAKBARRIER=2, LOG=0, MISSING=0, **SAFEFLAGS=0** (−10% CPU, A/B 2026-10-14). ALIGNED_ATOMICS=1 and FORWARD=1024 were noise and are not used. |
| FPS | Bench spot: 29–30 FPS, ≥92% of samples ≥28, even at 50 °C board temperature. The user saw ~20 FPS in heavier zones before the latest fixes; not re-measured there. |
| Stability | 6/6 clean boots after the DirectInput fix. The fix stores original vtable pointers per vtable and hooks Release. |
| Startup popup | The user gets an error at start and must press OK. Probably the game's own "network login failed" message (Goldberg, offline), not an app dialog. **Not confirmed**: no screenshot of it yet. |

## Agent DLL (`mod/dinput8/`)
- Source files: `dinput8.c` plus `ui.c` (included). Build in WSL:
  `x86_64-w64-mingw32-gcc -O2 -shared -o dinput8.dll dinput8.c dinput8.def -static-libgcc -lwinmm -ldxguid`
- Features:
  - tick patch + governor;
  - NoSkip pacer;
  - input caches;
  - event pool (CreateEventW/CloseHandle IAT hooks, **untested**);
  - chr LOD tuning;
  - sampling profiler;
  - adb command channel (`dsr_cmd.txt`: statelog / set / get / menubar / tab / closeall / tap / mouse, **untested**).
- Flag files in the game folder (`run-as com.remipelloux.gamenativecustom`, dir `CustomGames/DarkSoulsRemastered/`):
  - `dsr_nogov`: governor off.
  - `dsr_skip`: use the skip pacer.
  - `dsr_nopool`: event pool off.
  - `dsr_nodicache`: DirectInput cache off.
  - `dsr_lod.txt`: "full near dist"; `-1 0 0` = stock LOD.
  - `dsr_prof.go`: profiler trigger (seconds).
  - `dsr_vt.go`: pacer log.
- **Dev override:** the app copies `dinput8.dll.dev` (if present) over `dinput8.dll` on every start. Otherwise it copies the bundled asset.

## Phone state right now
- Installed APK: built 20:52. It contains an older agent (input cache, before the per-vtable fix) and the old controls.
- `dinput8.dll.dev` = newest agent (21:42 build: all features above).
- **Leftover flags from the stopped A/B:** `dsr_lod.txt` (= "-1 0 0", stock LOD) and `dsr_nopool`. Delete or set them on purpose.
- Container env has SAFEFLAGS=0. `BOX64_DYNAREC_PERFMAP` was removed.
- `adaptive_fast_charging` = 0 for tests. Restore it to 1 when the user wants.

## App (`opennative-src`, branch `dsr`)
- `ContainerUtils.kt` DSR block: Box64 env incl. SAFEFLAGS=0 (added after the 20:52 APK, so not built yet).
- `DsrLauncher.installAgent`: dev override.
- **New touch controls** by the controls agent:
  - `DsrTouchControls.java`, `controls-6.icp`, `InputControlsView.java`, `XServerScreen.kt` back gesture; doc in `docs/CONTROLS.md`.
  - Built once by that agent, **never installed or tested**.
- Build: `JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-17.0.20.101-hotspot"`, then `./gradlew :app:assembleLegacyDebug`. Copy `mod/dinput8/dinput8.dll` to `app/src/main/assets/dsr/dinput8.dll` first.

## Tools (`tools/`)
| Tool | What it does |
|---|---|
| `bench.sh LABEL SECS` | cold start → gameplay → move; logs FPS, timescale, cycles/frame |
| `abtest.sh` | A/B of env vars |
| `abfiles.sh` | A/B of agent flag files |
| `boottest.sh N` | N cold boots, checks the game stays alive |
| `profile.sh SECS NAME` + `stackprof.py` | in-game sampler, self/inclusive time per game function |
| `timescale.sh`, `pos.sh`, `setenv.sh` | IGT speed probe, player position, container env edits |
| `re/ghidra/perf.bat` | Ghidra no-analysis decompile; edit `perf_sites.txt`. Separate project `dsrperf`, so it does not clash with `dsrquick` |

## Next steps (in order)
1. **Finish the CPU A/B:** `bash tools/abfiles.sh 40 "lodstock:dsr_lod.txt=-1 0 0;dsr_nopool=1" "lod:-dsr_lod.txt" "lodpool:-dsr_nopool"`.
   - Keep LOD tuning (4/8/25) if cycles drop and distant enemies look fine.
   - Keep the event pool only if it gives a stable boot (`boottest.sh 4`) and fewer cycles.
2. **One APK with everything:** new agent + SAFEFLAGS + new controls. Install, run `boottest.sh 4`, then remove `dinput8.dll.dev` and the flags.
3. **Startup popup:**
   - Screenshot the start sequence: `adb exec-out screencap -p`. Strip the "Multiple displays" text before the PNG header.
   - If it is the game's network message: find the "launch offline" option byte, or skip the message via the agent.
   - If it is an app dialog: remove it in DSR mode.
   - Roadmap todo exists.
4. **UI runtime checks** (`docs/ui/UI_RE.md`, top-5 list), via `dsr_cmd.txt`:
   - Run `statelog 1` while opening menus.
   - Confirm the state ids, then switch `DsrGameState.poll()` to the state-table menu rule.
   - Then tap-to-click (`tap X Y`), slot loading (functional Load Game), tap-to-lock-on.
5. **More CPU** if heavy zones are still < 30:
   - profile there (`profile.sh`);
   - the character update is ~25% of the main thread;
   - job-sync waits ~16%.
6. **Docs:** keep `PORTING_LOG.md`, `RE_NOTES.md` and `PORTING_GUIDE.md` current. v0.5.0 = public release prep (ask before pushing).
