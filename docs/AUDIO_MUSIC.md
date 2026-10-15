# Music (OST) missing, SFX play — research 2026-10-15

## Findings (read-only, phone + PC files)
- **All game audio is one Pulse stream.** `pactl list sink-inputs` (run-as, `files/pulseaudio/pactl`): one input "DARK SOULS: REMASTERED", s16le 2ch 48 kHz, not muted, 100%. FMOD mixes music + SFX inside the game process (WASAPI: mmdevapi -> winepulse). Wine device format = 2ch 48 kHz float, mask 3. So Pulse / AAudio / Wine audio config / sample rate / 5.1 are **not** the cause.
- **FMOD streams the music, and the stream advances.** `/proc/<game>/fd` + `fdinfo pos` at Firelink (m10_02): `frpg_sm10.fsb` read at the offset of `m100200000.wav` (Firelink music, stereo MPEG 44.1 kHz) and `valley.wav` (stereo ambience); `frpg_xm10.fsb` (`y1000`, 6ch MPEG) too. Reads come in 192 KB chunks at play speed. File access, async I/O and the stream thread work: FMOD thinks the music plays.
- **Format split in the FSBs (all MPEG):** SFX = mono (mode 0x10100220, ~6000 samples). Music + ambience beds = stereo (0x10002240, `sm*` / `smain`); `xm*` = 6ch. Title music = `frpg_smain.fsb` (`config.wav`, `proto-opening.wav`, stereo).
- **Conclusion:** the music channel is decoded/mixed as silence inside FMOD (fmodex64.dll). Two things differ from SFX: (1) the stream path (decode in the FMOD stream thread, hand-off to the mixer thread through a ring buffer); (2) stereo/multichannel MPEG decode (other synth code). Both point at **Box64 dynarec code generation**, not files or audio config.
- **Box64 flags in use** (logcat ProcessHelper): preset PERFORMANCE `STRONGMEM=0 BIGBLOCK=3 FASTNAN=1 FASTROUND=1 X87DOUBLE=0 FORWARD=512 WAIT=1`; container `WEAKBARRIER=2 DIRTY=2 CALLRET=2 SAFEFLAGS=0`. Container env overrides the preset.
- **Timeline** (when music may have stopped): 10-13 20:31 first boot (Box64 0.4.2 COMPATIBILITY) -> 10-13 night 0.4.4 + PERFORMANCE + WEAKBARRIER=2 -> 10-14 DIRTY=2 CALLRET=2 -> 10-14 21:50 SAFEFLAGS=0 (APK 10-15 10:57). No doc mentions music before today.
- fmodex64.dll (image size 0x1c8000) loaded at 0x7ffe340000 in this boot (`/proc/<pid>/maps`), not at its base 0x180000000.

## Test plan (one batch; each test = `bash tools/setenv.sh ...`, cold start, listen at the title for 20 s)
User check per boot: title music yes/no. Also ask once: are Firelink music and wind/valley ambience (stereo streams) silent, while bonfire/footsteps (mono) play?
1. **Safe dynarec:** `BOX64_DYNAREC_STRONGMEM=1 BOX64_DYNAREC_WEAKBARRIER=0 BOX64_DYNAREC_FASTNAN=0 BOX64_DYNAREC_FASTROUND=0 BOX64_DYNAREC_SAFEFLAGS=1 BOX64_DYNAREC_CALLRET=0 BOX64_DYNAREC_BIGBLOCK=1 BOX64_DYNAREC_X87DOUBLE=1`. Music back -> dynarec flag; bisect 2-5. Silent -> go to 6.
2. `BOX64_DYNAREC_FASTNAN=0 BOX64_DYNAREC_FASTROUND=0` only (rest = current).
3. `BOX64_DYNAREC_STRONGMEM=1 BOX64_DYNAREC_WEAKBARRIER=0` only (stream thread -> mixer hand-off).
4. `BOX64_DYNAREC_SAFEFLAGS=1` only.
5. `BOX64_DYNAREC_CALLRET=0 BOX64_DYNAREC_BIGBLOCK=1` only.
6. **FMOD interpreted:** `BOX64_NODYNAREC=0x7ffe340000-0x7ffe508000` (check the fmodex64 range in `/proc/<pid>/maps` first; fix the range if it moved). Music back -> Box64 0.4.4 dynarec bug in FMOD code; keep this (FMOD is light) or narrow the range.
7. Still silent: `BOX64_DYNAREC_DIRTY=0` (slow boot), then Box64 0.4.2 (container `box64Version`), then `BOX64_DYNAREC=0` to the title only (very slow).
Reset after: `bash tools/setenv.sh BOX64_DYNAREC_WEAKBARRIER=2 BOX64_DYNAREC_CALLRET=2 BOX64_DYNAREC_SAFEFLAGS=0 -BOX64_DYNAREC_STRONGMEM -BOX64_DYNAREC_FASTNAN -BOX64_DYNAREC_FASTROUND -BOX64_DYNAREC_BIGBLOCK -BOX64_DYNAREC_X87DOUBLE -BOX64_NODYNAREC`. Then bake the winning flag into `ContainerUtils.kt` (DSR block) and re-run `tools/bench.sh` (FPS cost).

## Closed 2026-10-15 20:50
The stock PC build has no title music either (user check). Not a port bug: the investigation is closed.
