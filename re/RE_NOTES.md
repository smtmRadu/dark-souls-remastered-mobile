# DSR reverse-engineering notes (exe: DarkSoulsRemastered.exe 1.03.1, regulation 1.04)

Exe build = the one Dark-Souls-1-Overhaul targets: AOB `48 8B 05 ? ? ? ? 48 8B 48 68 48 85 C9 0F 84 ? ? ? ? 48 39 5E 10 0F 84 ? ? ? ? 48`
(DSR-Gadget WorldChrBase) resolves to RVA 0x1c77e50 = Overhaul `world_chr_man_imp`. So all Overhaul static offsets apply.
Module base 0x140000000 (no ASLR relocation seen). Second `.text` section at 0x2019000 = Arxan-protected code.

## Static pointers (RVA, deref once)
| Name | RVA | Source |
|---|---|---|
| WorldChrManImp | 0x1c77e50 | Overhaul + AOB verified |
| MenuMan | 0x1c88d98 | Overhaul |
| LockTgtManImp | 0x1c7a138 | Overhaul |
| PadMan | 0x1c6aea0 | Overhaul |
| CamMan (DSR-Gadget CamManBase AOB) | 0x1c6e188 | AOB in our exe |
| ChrFollowCam base (DSR-Gadget AOB) | 0x1c7a488 | AOB in our exe (= Overhaul bullet_man?) |
| FrpgSystem | 0x1b68e18 | Overhaul |

## Fields (found on PC bench, tools/pcgame.py)
| Field | Meaning | Verified |
|---|---|---|
| MenuMan+0x80 (i32) | main/title menu active = 1, in world = 0 | Overhaul + PC |
| MenuMan+0xA4 (i32) | saved-characters menu state | Overhaul |
| **MenuMan+0x50 (i32)** | **active in-game menu id: 0 none (gameplay), 8 menu bar, 2 inventory** | PC diff 2026-10-13 (only clean candidate in 0x3000 bytes) |
| LockTgtManImp+0x1430/0x1431 (u8) | bTargetLocked / _Alt | Overhaul |
| WorldChrMan+0x68 → PlayerIns | player | DSR-Gadget |

## Touch-layer rule
Controls visible ⇔ MenuMan+0x80 == 0 && MenuMan+0x50 == 0 && player loaded (+ not loading/cutscene: TODO).
| GameDataMan | 0x1c8a530 | +0xA4 = in-game time ms (stops on loading screens; = 1/30 s per frame, so speed = FPS/30 below 30). AOB 48 8B 05 ?? ?? ?? ?? 45 33 ED 48 8B F1 48 85 C0 |

## Frame timing (2026-10-14) — how the game advances time
| What | Address / layout | How found |
|---|---|---|
| Logic tick constant | `.rdata` 0x1412ccc78 = 1/60 (float). Loaded into xmm6 at 0x14015cec9 inside the per-frame function and passed to every system. **Agent patches it to 1/30.** | agent VEH + PAGE_GUARD on the IGT page → stack trace |
| Per-frame function | 0x14015ce90 (returns bool "keep running"), called in a loop from WinMain at 0x140137f30 | stack trace |
| Task/step update | 0x14024af10 (step manager, xmm1 = tick) → InGameStep::Update 0x14024f6b0 (xmm1) → 0x1402510d0 → WorldChrMan update 0x14036e400 → chr dispatcher 0x14036f610 | stack trace + xref.py |
| IGT update | 0x140758a30: `IGT += (int)(tick*1000)` at 0x140758c5e, clamp 0xd693a018 | scan for writers of GameDataMan+0xA4 |
| Frame pacer | `FrpgFlipper_*` (RTTI). vtables: 60FPS 0x1412ab268, 30FPS 0x1412ea688, 60FPS_NoSkip 0x1412ea7e8, 30FPS_NoSkip 0x1412ea790, 140FPS 0x1412ab2c0, base 0x1412ea630. Object = 16 bytes {vtable, flag}. Slot 8 sets vsync thresholds (60FPS: 55/60, 0.95), slot 9 = skip rule (`(n-1) <= 1` → max 2 ticks per frame). **Agent swaps the live object to 30FPS.** | RTTI names → COL → vtables |
| Pacer manager | task object, vtable 0x1412ea400: +0x20 mode (4 = 60FPS; game re-applies it every frame), +0x28 FrpgFlipper*. Factory switch at 0x140203f69 (0→30FPS, 1→DS1/PAL, 2→30FPS_NoSkip, 3→60FPS_NoSkip, 4→60FPS, 5→140FPS) | ctor xrefs |
| Pacer slots (runtime log via wrapped vtable) | slot 9(self, ctx): ctx = 3 QPC stamps + n at +0x20; if n∈{1,2} sets flag → slot 3 returns 0 next frame (render/skip switch). It does **not** set the tick count. | agent copies the vtable, wraps slots 3/9 |
| Speed governor (final fix) | ticks per frame vary with load (fixed 1/30 tick gave 1.26–1.44× at 28–30 FPS). Agent every 0.5 s: ticks = ΔIGT / (int)(tick·1000), tick := real/ticks (EMA 0.5, clamp 1/60…1/10). Measured 0.99–1.00× at 17 and 28 FPS. | `governor()` in dinput8.c |
| Frame skip (key finding) | per-frame fn 0x14015ce90 = exactly **one logic tick** (no inner loop). The skip flippers (60FPS, 30FPS) set a flag when a frame took 2 periods → the next frame runs logic without rendering. Measured 45 ticks/s for 30 renders/s. **Agent uses FrpgFlipper_30FPS_NoSkip (0x1412ea790)** → 1 tick per render (30 ticks/s), governor keeps 1×. | wrapped-vtable log + governor ticks/s |
| Chr update LOD | 0x14036e8d0 sets chr+0x164 = update interval (0 every tick, 2, 5, 30; -1 off); dispatcher 0x14036f610 updates a chr when `tick % interval == phase` with dt×interval. Knobs in [0x141c77e88]: +0x2c full-rate count (10), +0x30 near count (20), +0x34 distance m (40). Agent sets 4 / 8 / 25 (dsr_lod.txt overrides). | Ghidra quick decompile + memtool read |
| Result | speed = ticks per second × tick. 60 ticks/s × 1/60 before; with patch 30 ticks/s × 1/30 → real-time at 30 FPS with half the logic work, still real-time down to 15 FPS (2 ticks/frame) | timescale.sh: 1.04 at 14.6 FPS |

Dead ends (kept for the record): the raw frame delta float in a DLL heap object (0x30703fd0 on PC, written by a system DLL); ring of per-chr-LOD interval nodes (n × tick); loading scheduler (QPC freq/60 budget, 0x14059e3xx); worker dispatcher 0x140d8df80; render command builder 0x140160890.

## Main-thread CPU (in-game sampling profiler, 2026-10-14)
`tools/profile.sh` + `tools/stackprof.py` (agent suspends the main thread ~400 Hz, RtlVirtualUnwind).
| Cost | Where | Fix |
|---|---|---|
| 13% | GetAsyncKeyState × 236 keys per frame, 0x140ca06a0 (loop at 0x140ca06d9); each call = wineserver round trip | IAT hook → key table refreshed by the agent at 20 Hz |
| ~1% | SystemParametersInfoA(SPI_GETMOUSE / SPI_SETMOUSE+SPIF_SENDCHANGE) every frame, 0x140ca1006 | IAT hook: GET from cache, SET dropped |
| ~9% | DirectInput Poll (slot 25) + GetDeviceState (slot 9) on 1 A + 7 W devices every frame (0x140ca0f88, 0x140ca0fdf, 0x140e2aec7, 0x140e2bd14…) | proxy hooks CreateDevice → device vtables; state served from a cache polled at 100 Hz (mouse deltas summed) |
| ~40% | logic: step manager 0x14024af10; chr dispatcher 0x14036f610 = 23% | next target |
| ~16% | main thread waits for worker jobs (0x1408f0363/083d/08ec → 0x1409171xx) | next target |
Result (same spot, hot phone): 17.2 → 28.1 FPS, 125M → 72M cycles/frame.

## Equipment, quick items, spells, inventory (verified on the phone 2026-10-15, exe 1.03.1)
PlayerGameData `PGD = [[0x141c8a530]+0x10]`. EquipGameData = PGD+0x280 (layout = Overhaul `PlayerInsStruct.h`, matches DSR).
| Address | Meaning | Example |
|---|---|---|
| PGD+0x308 | weapon style (1 = normal; 2H states differ) | 1 |
| PGD+0x30c / +0x310 | left / right hand selector (0 = slot 1, 1 = slot 2) | 0 / 0 |
| PGD+0x324 + i*4, i<20 | equipped item **ids**: 0 L1, 1 R1, 2 L2, 3 R2, 4-7 arrows/bolts, 8 head, 9 body, 10 arms, 11 legs, 12 hair, 13-14 rings, 15-19 quick items | L1 1462000 Spider Shield, R1 701000 Battle Axe, Q1 203 Estus +1 |
| PGD+0x2a4 + i*4 | same 20 slots → inventory index | 75, 76, …, Q1 77 |
| PGD+0x3d8 | inventory list ptr (same value at +0x3d0) (entries 0x1c: +3 category byte, +4 item id, +8 quantity). Indexes 0-63 = keys, 64+ = items | [77] = 203 ×10 |
| PGD+0x3e0 / +0x3e4 | item count / key count | 41 / 4 |
| PGD+0x438 + i*4, i<5 | quick bar → inventory index | 77, -1… |
| PGD+0x44c | selected quick item → inventory index | 77 |
| [PGD+0x418]+0x18 + i*8, i<12 | attuned spells {magic id, casts left} | all -1 |
| [PGD+0x418]+0x78 | selected spell slot | |
HUD: right hand id = slot[2*R+1], left = slot[2*L], quick item = inventory[PGD+0x44c].
