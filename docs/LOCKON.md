# Tap-to-lock (tap an enemy → lock on to it)

Goal: tap an enemy on the phone → lock on to that enemy. Tap the locked enemy or empty space → unlock.
Today `DsrTouchControls.lockOn()` pulses R3 and the game picks the target.

Exe: DSR 1.03.1 (regulation 1.04), image base 0x140000000. All addresses are absolute.
Confidence: **S** = static only (decompile/disasm), **C** = confirmed by a second source (Overhaul, DSR-Gadget,
SoulSplitter), **RT** = needs a runtime check on the phone.
Decompiles: `re/ghidra/lockon_funcs.c`, `re/ghidra/lockon_funcs2.c` (Ghidra headless, own project `dsrlock`,
`QuickTimerFuncs.java`). Disasm helpers: `re/xref.py`, `re/ui/fields.py`.

**Verdict: feasible.** The game already has everything: a list of lockable candidates with world positions, a
"current target" flag that wins the next selection, and a camera with matrix + FOV at a static path. The app reads
candidates + camera, picks the entry under the finger, and the agent sets two bytes on the game thread.
No game function call is needed.

---

## 1. Enemies

### 1.1 Use the lock candidate list (recommended)

`LockTgtMan::Update` (0x14040b0f0, called every tick from the WorldChrMan update) builds this list.
It already filters what the game allows you to lock: hostile team, lock point enabled, in range, not the player.
So the app does not need its own hostility logic.

```
lt   = u64(0x141c7a138)                 LockTgtManImp*                      (C: Overhaul + RTTI)
e    = u64(lt + 0x10)                   first candidate entry (0 = none)    (S)
next = u64(e  + 0x30)                   linked list; pool of 64 entries      (S)
```

Candidate entry (0x50 bytes, S, from 0x14040b0f0 / 0x14040c2c0):

| Off | Type | Meaning |
|---|---|---|
| +0x00 | vec4 | world pos of the lock point (copied from the lock point every tick; use w = 1) |
| +0x10 | f32 | distance to the player |
| +0x14 | f32 | player-facing dot |
| +0x18 | f32 | distance to the camera |
| +0x1c | f32 | camera-facing dot |
| +0x20 | f32 | line-of-sight recheck timer |
| +0x24 | f32 | LOS grace timer (current target stays locked while blocked) |
| +0x28 | f32 | score |
| +0x30 | ptr | next entry |
| +0x38 | ptr | lock point (see below) |
| +0x40 | u8 | flags: 0x01 heap, 0x02 free, 0x08 seen this tick, **0x10 lockable now**, **0x20 target / best**, **0x40 LOS blocked**, 0x80 LOS checked this tick |

Correction to `docs/ui/UI_RE.md` §3: +0x10 is the distance (not an id), and 0x40 means LOS **blocked**
(the selection skips 0x40 entries; the stick switch 0x14040c2c0 requires `(flags & 0x60) == 0`).

Lock point (`[0x141c7a130]+0x10` list, linked by +0x18; S):

| Off | Type | Meaning |
|---|---|---|
| +0x00 | vec4 | world pos |
| +0x10 | u8 | extra range (added to the lock range) |
| +0x11 | u8 | flags: bit0 enabled, bit2 drop unless current target |
| +0x12 | i16 | ref count |
| +0x14 | u32 | owner ChrIns handle (class `0x1xxxxxxx`). Owner = `0x14040a480(lockpoint)` |

A boss can own several lock points (several entries with the same handle). Key the pick by **lock point address +
handle**, not by handle alone.

**Tap-eligible entry:** `(flags & 0x50) == 0x10` (lockable now, not blocked), or the current target
(`flags & 0x20` and `lt+0x1430 != 0`). Other entries cannot win the selection, so a tap on them would lock
something else.

Filters inside `LockTgtMan::Update` (S): lock point bit0; owner ≠ player; `0x1402d9280(player, chr) == 1`;
distance < `lt+0x152c` (lock range) + `lt+0x1520` + lock point +0x10.
`0x1402d9280` = relation table `byte[0x141a2b020 + team(player)*19 + team(chr)]`, team = `0x140322380(chr)` =
`ChrIns+0xd8` (forced to 15 by special effect 0x84). Row 1 (human player) locks teams 3, 6, 7, 9, 10, 11, 13, 14,
16, 17, 18; not 8 (ally NPCs). So friendly NPCs never enter the list.

### 1.2 All loaded characters (debug overlay only)

| What | Address / path | How found | Conf |
|---|---|---|---|
| WorldChrMan | `wcm = u64(0x141c77e50)` | Overhaul + AOB | C |
| Player | `u64(wcm+0x68)` (`0x140371ed0`: override `[0x141c77e88]+0xf0` first) | DSR-Gadget + disasm | C |
| Chr sets | `n = i32(wcm+0x180)`; set i = `u64(wcm+0x188 + i*0x18)` | chr dispatcher 0x14036f610, 0x1405c7015 | S |
| Chrs in a set | `cnt = i32(set+0)`; `chr = u64(u64(set+8) + j*0x38)` (`0x14033ec10`) | disasm | S |
| Handle → ChrIns | blk = `(h>>14)&0x3f`, idx = `h&0x3fff`; set = `u64(wcm+0x440+blk*8)`; `u64(u64(set+8)+idx*0x38)` (`0x1403714b0`) | decompile | S |
| ChrIns handle | `u32(chr+0x08)` (`0x1403222a0` passes it to the manipulator) | decompile | S |
| ChrType | `i32(chr+0xd4)` (`0x140322180`, Overhaul `get_player_chr_type`) | both | C |
| TeamType | `i32(chr+0xd8)` (`0x140322380`) | disasm | S |
| HP / max HP | `i32(chr+0x3e8)` / `+0x3ec` (alive = HP > 0) | Overhaul + SoulSplitter | C |
| Position | `f32x3(u64(u64(chr+0x68)+0x28)+0x10)` (ChrCtrl → physics) | SoulSplitter (player); same class for NPCs | C player, S others |
| Update LOD | `i32(chr+0x164)` (-1 = not updated) | RE_NOTES | S |

Skip the player (`chr == u64(wcm+0x68)`), HP ≤ 0, and use the relation table above for hostility.
The tap logic itself should use §1.1, because only those entries can be locked.

---

## 2. Camera and projection

Use the gameplay camera **ChrCam** (RTTI `NS_FRPG::ChrCam`, vtable 0x1412eebe8). The game's own stick-switch
(0x14040c2c0) projects candidates with it.

| What | Path | How found | Conf |
|---|---|---|---|
| ChrCam | `cam = u64(lt + 0x1438)` | `InGameStep` writes `InGameStep+0x68` there (0x14024e7d3); ctor 0x1402345c0 sets the ChrCam vtable | S |
| ChrCam (2nd path) | `cam = u64(u64(0x141c7a488) + 0x60)` | same write site; DSR-Gadget `ChrFollowCamAOB` matches it (Gadget then adds +0x60 → ChrFollowCam) | C |
| World matrix | `cam+0x10..+0x4f`: 4 rows × vec4, row-vector convention; row 3 (`+0x40`) = position | `0x1400b6d90` copy, `0x1400b6d60` = inverse → view | S |
| Projection | `cam+0x50` fovY (rad), `+0x54` aspect, `+0x58` near, `+0x5c` far → D3D LH perspective `0x14007c1c0` | decompile | S |
| Render size | `rs = u64(0x141b68ec8)`; `W = f32(rs+0x6f0)`, `H = f32(rs+0x6f4)` (`0x14015e890`) | decompile | S |
| Reticle pixel cache | `f32 0x141c84110` x, `0x141c84114` y (render px) of the locked target; written by `0x1406705c0` | decompile | S |

Other camera sources (not needed): CameraMan `u64(u64(0x141c6e188)+0x10)` = GetCamera(1);
the reticle uses `[[InGameStep+0x58]+0x18]`. They may equal ChrCam (RT).

### Math (same as the reticle code 0x1406705c0)

```
M     = 4x4 rows from cam+0x10 (r0, r1, r2, r3=pos)
View  = inverse(M)                      // 0x14007bcb0 = general 4x4 inverse
f     = 1 / tan(fovY / 2)
Proj  = | f/aspect 0  0           0 |
        | 0        f  0           0 |
        | 0        0  far/(far-near)        1 |
        | 0        0  -near*far/(far-near)  0 |
v     = [x y z 1] · View                // view space, +z forward
if v.z <= near → behind the camera, skip
ndcX  = v.x * (f/aspect) / v.z
ndcY  = v.y * f / v.z
px    = (ndcX * 0.5 + 0.5) * W          // consts 0x1412e6000 (0.5,-0.5,0.5), 0x1412e5ff0 (0.5,0.5,0.5)
py    = (-ndcY * 0.5 + 0.5) * H
```

Shortcut when the rows are orthonormal (rigid camera): `d = p - r3; v = (d·r0, d·r1, d·r2)`.
Use the full inverse until a runtime check proves the rows are orthonormal.

Phone mapping: the game frame (W × H, 16:9) is letterboxed into `rect` on the screen:
`sx = rect.left + px / W * rect.width`, `sy = rect.top + py / H * rect.height`.

Validation: when locked, project the 0x20 entry and compare with the reticle cache `0x141c84110/14`.
They should match within a few pixels (both use render px).

---

## 3. Lock-on state and how to set it

| What | Address | How found | Conf |
|---|---|---|---|
| Locked | `u8 lt+0x1430` | Overhaul `bTargetLocked` + `0x14040d200` | C |
| Lock request | `u8 lt+0x1431`. InGameStep sets `= !lt+0x1430` on the lock button (0x14024fd15) | decompile | C |
| Force unlock | `u8 lt+0x1432` | `0x14040b0f0` | S |
| Lock allowed / applied to player | `u8 lt+0x156b` / `lt+0x156c` (0 = disabled) | `0x14040b0f0` | S |
| Switch cooldown | `f32 lt+0x1440` (stick switch sets 0.5) | `0x14040c2c0` | S |
| Current target entry | `0x14040d200(lt)`: first entry with flag 0x20 while `lt+0x1430 != 0` | decompile | S |
| Current target handle | `u32(u64(entry+0x38)+0x14)` | S |
| Player side | `0x1403222a0(player, 1, chr)`: `player+0x1a0` = locked, manipulator vfunc +0x48(chr handle) → ChrManipulator `+0x220` LockonTargetHandle; `player+0x1b0` = target pos | decompile + Overhaul `PadManipulatorStruct.h` | S / C |

### How `LockTgtMan::Update` picks the target (per tick, main thread)

1. `+0x1432` set → clear 0x1430/0x1431. Then `+0x1430 = +0x1431` (request becomes state).
2. Rebuild the candidate list from lock points (entries keep their flags).
3. Recompute 0x10 / 0x40 per entry.
4. Score entries with 0x10. An entry with **0x20 while locked gets the max score** (`0x141340a60` = 3.37e38).
   Clear 0x20/0x08 on all, then set 0x20 on the best entry that is not 0x40-blocked.
5. Locked + best found → `0x1403222a0(player, 1, owner(best))`. Locked + none → unlock.
6. Stick-flick switch (`0x14040c150` → `0x14040c2c0`): moves 0x20 from the old to the new entry, sets the 0.5 s cooldown.
   Step 4 of the next tick then keeps the new one. **Tap-to-lock copies this mechanism.**
7. `+0x1431 = +0x1430`.

There is no "lock chr X" function. Writing player fields directly is overwritten in step 5 every tick.

### Agent-side lock (recommended)

Run on the game's main thread between two `LockTgtMan::Update` calls. The candidate list and flags are only
changed on the main thread, and an entry can be freed/reused by step 2; a write from the agent thread can race
the flag clear in step 4 or hit a recycled entry.

Main-thread hook already in the agent: `hook_getstate` (DirectInput GetDeviceState, called by the game every
frame on the main thread, `dinput8.c`). Call `lock_apply()` from there (idempotent per request; it runs once per
device call). Alternative: the FeShortcut `Update` vtable hook in `hud.c`.

```c
#define P_LOCKTGT 0x141c7a138ULL
static volatile LONG lock_seq, lock_done;   /* agent thread bumps lock_seq after filling the fields */
static uint64_t lock_lp; static uint32_t lock_handle; static int lock_mode;  /* 1 lock, 0 unlock */

static void lock_apply(void) {              /* main thread only */
    LONG s = lock_seq; if (s == lock_done) return; lock_done = s;
    uint8_t *lt = *(uint8_t **)P_LOCKTGT; if (!lt) return;
    if (!lock_mode) { lt[0x1431] = 0; return; }
    uint8_t *pick = NULL; int n = 0;
    for (uint8_t *e = *(uint8_t **)(lt + 0x10); e && n < 64; e = *(uint8_t **)(e + 0x30), n++) {
        uint8_t *lp = *(uint8_t **)(e + 0x38);
        if ((uint64_t)lp == lock_lp && lp && *(uint32_t *)(lp + 0x14) == lock_handle) pick = e;
    }
    if (!pick || (pick[0x40] & 0x50) != 0x10) { logmsg("lock: %llx gone/not lockable", lock_lp); return; }
    n = 0;
    for (uint8_t *e = *(uint8_t **)(lt + 0x10); e && n < 64; e = *(uint8_t **)(e + 0x30), n++) e[0x40] &= ~0x20;
    pick[0x40] |= 0x20;
    *(float *)(lt + 0x1440) = 0.5f;         /* same cooldown as the stick switch */
    lt[0x1431] = 1;                          /* request lock; no-op if already locked */
}
```

Why it works: step 1 turns `+0x1431 = 1` into `+0x1430 = 1` before scoring, so the picked 0x20 entry gets the
max score on the same tick (also when not locked before). Already locked on another enemy: the same flag move
switches the target (what the stick switch does).

Unlock: `lt[0x1431] = 0` (same as pressing the lock button while locked). `lt[0x1432] = 1` also works (force).

---

## 4. Plan

### 4.1 App (`DsrGameState.kt`)

Add a `lockScan()` to the 100 ms poll in GAMEPLAY phase (and on demand on tap, see 4.3):

1. `lt = u64(0x141c7a138)`; walk `+0x10` / `+0x30`, max 64 entries. Store per entry: entry addr, lock point
   (`+0x38`), handle (`u32(lp+0x14)`), pos (`+0x00`), flags (`+0x40`).
   Validate pointers (non-zero, user range) and stop on loops: reads race the main thread.
2. `locked = u8(lt+0x1430) != 0`; current = entry with flag 0x20 when locked.
3. `cam = u64(lt+0x1438)`; read 0x10..0x5f (80 bytes, one read). `W, H` from `[[0x141b68ec8]+0x6f0]`.
4. Use bulk reads (`readFully` of 0x50 per entry) to keep the poll cheap.

### 4.2 Touch (`DsrTouchControls.lockOn(x, y)`)

1. Re-read candidates + camera now (one fresh scan, ~2 ms), so the pick uses this frame's camera, not a 100 ms old one.
2. For each tap-eligible entry (§1.1): project (§2), skip `v.z <= near`, map to screen (letterbox rect).
3. Pick the entry with the smallest screen distance ≤ 48 dp. Prefer the higher on-screen point on ties
   (several lock points of one boss).
4. Decide:
   - pick == current target → `unlock`
   - pick found → `lock <lp> <handle>`
   - no pick, locked → `unlock`
   - no pick, not locked → nothing (or keep the old R3 pulse as a fallback: the game picks).
5. Agent missing (no ack in 300 ms, see 4.3) → fall back to the R3 pulse.

### 4.3 Channel app → agent

Option A (simple, ≤ 50 ms): a dedicated file `dsr_lock.txt` in the game folder (`DsrLauncher.gameDir()`; the
agent's cwd, same folder as `dsr_cmd.txt`). The app writes `dsr_lock.tmp` and renames it to `dsr_lock.txt`
(atomic). Content: `<seq> lock <lp hex> <handle hex>` or `<seq> unlock`. The agent's 50 ms loop reads and
deletes it, fills `lock_lp/lock_handle/lock_mode`, then bumps `lock_seq`. Do not reuse `dsr_cmd.txt`: adb tests
write it too, and read+delete can drop a line written in between.

Option B (fastest, ≤ 1 frame): a 64-byte shared file `dsr_lock.bin`, created by the agent and mapped with
`CreateFileMapping/MapViewOfFile` (Wine maps the unix file `MAP_SHARED`). The app writes the record with
`RandomAccessFile` (`seq` written last). `lock_apply()` on the main thread reads the mapped `seq` directly each
frame: no syscalls, no agent-thread hop. Page-cache coherence makes `write()` visible to the mapping (RT).

Ack: the agent writes `lock_done` and the result (`ok`, `gone`, `not lockable`) into `dsr_lock.ack` (A) or the
second half of `dsr_lock.bin` (B). The app also sees the result directly: `lt+0x1430` and the 0x20 entry on the
next poll.

Start with A; switch to B if the 50 ms + 100 ms delay feels slow.

### 4.4 Agent (`ui.c` / `dinput8.c`)

1. `lock_poll()` in the 50 ms loop (option A file) → fills the request, bumps `lock_seq`.
2. `lock_apply()` (above) called from `hook_getstate`.
3. Log every request and result to `dsr_agent.log`.
4. adb test commands in `dsr_cmd.txt`: `lockdump` (log entries: lp, handle, pos, flags, projected px with ChrCam,
   reticle cache), `lockidx N` (lock the N-th eligible entry), `unlock`.

---

## 5. Risks and open questions

| Risk | Mitigation |
|---|---|
| ChrCam matrix ≠ render camera (shake, cut-scene cams, the reticle uses `[[InGameStep+0x58]+0x18]`) | Validate with the reticle cache 0x141c84110; switch to CameraMan GetCamera(1) if it fits better. 48 dp tolerance hides small offsets |
| Camera rows not orthonormal | Use the full inverse (§2) |
| Lock point w ≠ 1 | Force w = 1 in the app |
| Main thread is not the GetDeviceState caller under Box64/Wine | Log `GetCurrentThreadId()` vs `main_tid` once; fall back to the FeShortcut Update hook (menu update, main thread) |
| Entry recycled between app scan and agent apply | Agent re-finds the entry by lock point + handle and checks `(flags & 0x50) == 0x10` |
| Target becomes LOS-blocked or leaves range | The game drops it itself (same as normal lock); the app just shows the state |
| `lt+0x156b == 0` (lock disabled: cut-scene, menu) | Agent skips; app falls back / ignores |
| `0x141a2b020` team table and team ids are static only | Not needed for tap (game filters); needed only for the debug overlay |
| Arxan integrity checks | We only write heap data (LockTgtMan), no code or .rdata |

---

## 6. Phone test checklist

1. **Read path (app only).** Log entries every second at Undead Burg: count, handle, pos, flags. Expect 0–6 entries
   near enemies, flags 0x18 on lockable ones, none for the player or friendly NPCs (Solaire, merchant).
2. **Camera.** Lock with R3, project the 0x20 entry, compare with `0x141c84110/14`. Expect ≤ 3 px error in render px.
   Turn the camera; error stays small. Check `v.z <= near` rejects an enemy behind you.
3. **Overlay.** Draw a debug dot on each projected entry (app overlay). Dots sit on enemies' chests while you walk and turn.
4. **Agent apply.** adb `lockidx 0`, `lockidx 1`: the reticle jumps to each; `lt+0x1430 = 1`. `unlock`: reticle off.
   Log shows `lock_apply` on the main thread id.
5. **Tap.** Two enemies side by side: tap each → lock follows the finger. Tap the locked one → unlock.
   Tap empty sky while locked → unlock. Tap empty while unlocked → nothing (or R3 fallback).
6. **Edges.** Enemy behind a wall (0x40): tap is ignored. Enemy out of range: ignored. Boss with several lock points
   (e.g. Taurus Demon, Gaping Dragon): nearest point wins. Enemy dies while locked: game unlocks, app shows it.
   Tap during a menu / cut-scene: no change.
7. **Latency.** Time from tap to reticle (screen record). Target: ≤ 150 ms with option A, ≤ 50 ms with option B.
8. **Stability.** 10 minutes of tap-locking in a fight, then zone change + bonfire rest + death: no crash, list
   resets cleanly (`lt+0x10` = 0 during loading).
