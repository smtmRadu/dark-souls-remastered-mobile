# Policy — DarkSoulsRemasteredAndroid

## Conventions
- Game copy lives in `Dark.Souls.Remastered.v1.04/`; original stays in `C:\Games\Dark Souls\...` untouched.
- `PLAN.md` = original plan; this roadmap overrides it where they differ.

## Constraints
- Private use only: never share the APK or game files.
- Play offline.

## Decisions
- 2026-10-15: check phone temperature before each test boot (battery < 42 °C, xo-therm < 50 °C); stop the game between batches. Many back-to-back boots heated it to 62 °C skin / 49.5 °C battery.
- 2026-10-15: phone heat is the render budget: GPU <= 50 % in gameplay (DsrGpuGovernor), post effects off. Never raise RENDER_BUDGET without a 15-min heat test (2.0x hit ~70 °C + throttling, docs/PORTING_LOG.md).
- 2026-10-15: batch changes; one phone game boot verifies the whole batch (restarts are slow).
- 2026-10-13: Use the local v1.04 copy with its Steam emulator; no Steam client in the APK for now — user wants to see it running first.
- 2026-10-13: Order = run on phone first, reverse engineering only later for the touch controls.
- 2026-10-13: No Winlator UI or stock-Winlator testing — a dedicated "Dark Souls" APK only; the translation layer stays hidden inside it.
- 2026-10-13: Controls must feel native (tap enemy = lock-on, touch item bar), done via an in-game mod DLL, not an overlay.
- 2026-10-13: Performance target 60 FPS (user saw ~0.3x speed in Winlator before). Prefer ARM64EC Wine + FEX over plain Box64.
- 2026-10-13: Game files live in app-internal storage only; never run them from /storage/emulated/0 (FUSE crash on Android 16 + slower I/O).
- 2026-10-13: Build the APK with targetSdk 28 (OpenNative 'legacy' flavor): DSR's anti-tamper needs writable code pages; SDK 29+ W^X rules make it hang.
- 2026-10-13 (revised 21:16): User now wants MAX phone performance (Samsung profile not Light) with the game capped at 30 FPS. Stable 30 matters: DSR game logic slows down (timescale < 1) when FPS drops.
- 2026-10-13: Order after 30 FPS: (1) bake config into the APK, (2) document all experiments as a reusable porting guide for other games, (3) reverse engineer + design native-style controls.
- 2026-10-13: Controls: no default gamepad overlay. Controls show only when needed (hidden in menus/cutscenes), like a native mobile game.
- 2026-10-13: User granted full auto mode until the project is done (user asleep). Follow the roadmap; record every decision/experiment in .track.
- 2026-10-13 22:30: FPS work order: non-visual optimizations first (refresh rate, core choice, Box64/DXVK/Wine tuning, engine knobs); reduce graphics only as a last resort, cheapest-looking settings first. A cool phone beats max settings.
- 2026-10-13: Control design is finalized in design/final_wanted_controls.html (artifact https://claude.ai/artifact/5zE3Hd3kZPu3SaRwj36Qo8); its Decided table is the spec for v0.4.0.
- 2026-10-13: Equipment slots are drawn natively by the APK (DLL reports equipped items/counts; icons extracted from game menu textures); the game's stock slot block is hidden.
- 2026-10-14: The code will be published on GitHub so other owners can apply our edits to their own copy. Publish only our code, patches, offsets and docs — never game files, exe, saves or Steam-emulator files. Ask before pushing.
- 2026-10-14: Document every search and finding (what worked, what failed, how it was found): we will port another game after this one.
- 2026-10-14: Target: constant 30 FPS and real-time (1x) game speed. 1x reached via the in-game agent (logic tick 1/30 + 30FPS pacer).
- 2026-10-14 21:45: 1x is now kept by the agent's speed governor (tick length tracks real time) + FrpgFlipper_30FPS_NoSkip (1 logic tick per rendered frame). Supersedes the fixed 1/30 tick.
- 2026-10-14 21:10: User asleep — full autonomy, no questions. Parallel subagents allowed (Opus 5.5 everywhere). Phone belongs to the main session only.
- 2026-10-15: v1.0.0 release = a mod set of all our changes + a small patcher program that applies it to a user's bare game copy (they port it themselves). Track every game/prefix/container change so the patcher can reproduce it.
- 2026-10-15: No black bars long-term: patch the game to render at the phone's aspect ratio (Hor+, wider FOV, no stretch) instead of styling the bars (edge glow becomes a fallback).

- 2026-10-15: Native ARM64 rebuild (decompile + recompile to an APK) is the last milestone (v2.0.0), after the v1.0.0 patcher.
- 2026-10-15: UI testing stays on the phone (Android emulator not viable: ARM64-only Box64/Wine; PC-game testing considered, user chose the phone).
- 2026-10-15: The user's current save is the dev save for controls / menu work. Back it up with `tools/devsave.sh pull` and restore it with `devsave.sh push` after tests that change the save (New Game / cutscene tests use a separate save).
- 2026-10-15: Never write the game's .text (anti-tamper kills the game ~2 s later). Change behaviour through .data / .rdata pointers (vtables, handler tables) instead.
- 2026-10-16: Development loop = docs/DEV_PROCESS.md: batch edits, one restart, every feature verified with screenshots by Claude (user should not test each step by hand).
