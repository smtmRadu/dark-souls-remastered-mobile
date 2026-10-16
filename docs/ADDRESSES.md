# DSR address registry

This file lists every game address and struct offset that the port reads or writes.
Use it to find which address changes which game behaviour.

- Exe: `DarkSoulsRemastered.exe` from `Dark.Souls.Remastered.v1.04/`. Code comments call the build "1.03.1" (regulation 1.04). It is the same file.
- Image base: `0x140000000`. Box64 maps the exe 1:1, so all addresses are absolute.
- Sections (from the PE header): `.text` 0x140001000-0x14129c400, `.rdata` 0x14129d000-0x141a24c00, `.data` 0x141a25000-0x141d0af78, `.idata` 0x142010000-0x142018c00, second `.text` (Arxan) 0x142019000-0x14319b000.
- Writers: only the agent DLL (`mod/dinput8/*.c`, runs inside the game). The Android app (`DsrGameState.kt`) can only read (`/proc/<pid>/mem`, SELinux blocks writes).
- Notation: `[X]` = read the 8-byte pointer at X. `R` = read, `W` = write. "Agent" = `mod/dinput8/`, "App" = `opennative-src/app/src/main/java/app/gamenative/dsr/`.

> **Rule: never write `.text`.** The anti-tamper kills the game about 2 s later (tested 2026-10-15, NOP of the offline-notice call). Change behaviour through `.data` / `.rdata` values, vtable slots, handler-pointer tables and heap objects. `.rdata` writes need `VirtualProtect(PAGE_READWRITE)` first. All current patches follow this rule.

Sources: `re/RE_NOTES.md`, `docs/ui/UI_RE.md`, `docs/ui/FONTS_RE.md`, `docs/ui/ASPECT_RATIO.md`, `docs/LOCKON.md`, `docs/PORTING_LOG.md`, `re/ui/menu_ids.txt`.

---

## 1. Managers / singletons (static pointers in `.data`)

| Address | Section | R/W | Who | What it is | Notes |
|---|---|---|---|---|---|
| `0x141c88d98` | .data ptr | R | Agent `ui.c:ms_get/ms_set/ui_log_state_diff`; App `DsrGameState.poll` (`MENU_MAN`) | `MenuMan*`. Menu state array at +0x30 (section 3). | 0 = not built yet; the app treats 0 as LOADING. |
| `0x141c8a530` | .data ptr | R | Agent `dinput8.c:governor/trace_igt`, `hud.c:menu_hud`, `display.c:pin_display`; App `poll` (`GAME_DATA_MAN`) | `GameDataMan*`. Fields in section 4. | |
| `0x141c77e50` | .data ptr | R | App `poll` (`WORLD_CHR_MAN`) | `WorldChrManImp*`. +0x68 = player `ChrIns*`. | App: ptr 0 or player 0 = LOADING. |
| `0x141c77e88` | .data ptr | R | Agent `dinput8.c:apply_lod` | Character-update LOD knob block (section 11). | |
| `0x141c7a138` | .data ptr | R | Agent `lock.c:lock_apply`; App `readLockScan` (`LOCK_TGT_MAN`) | `LockTgtManImp*` (section 8). | |
| `0x141c7a488` | .data ptr | R | Agent `cam.c:follow_cam` | Chr camera root. `[[[0x141c7a488]+0x60]+0x60]` = ChrExFollowCam (section 7). | DSR-Gadget ChrFollowCam AOB. |
| `0x141c6aea0` | .data ptr | R | Agent `ui.c:ui_mouse_mode` | `PadMan*`. +0x68 = KB/mouse mode byte (section 10). | |
| `0x141c71970` | .data ptr | R | App `poll` (`REMO_MAN`) | `RemoMan*` (real-time cutscene player). Byte +0x150 = cutscene plays; +0x151 / +0x152 = other remo bytes (getters 0x14028e440 / 0x14028e460, unknown). | Found 2026-10-16 via the debug event test `EcTestRemoPlaying` (vtable 0x141400950, slot 1 calls getter 0x1404917b0). App: cutscene = GAMEPLAY with only the Skip button. |
| `0x141b68ec8` | .data ptr | R | App `readLockScan` (`RENDER_SIZE`) | Graphics object. +0x6f0 / +0x6f4 = render width / height (float). | Set once at graphics init. |

## 2. Menu: dialog objects and vtables

Dialog vtable slot 16 (`vt+0x80`) = `Update(this, float dt)`. The agent swaps that slot (vtables are in `.rdata`, `VirtualProtect` first) and calls the original.

| Address / offset | Section | R/W | Who | What it does / what changing it does | Notes |
|---|---|---|---|---|---|
| `0x1413afe10` (+0x80 = `0x1413afe90`) | .rdata vtable | W slot 16 | Agent `hud.c:hook_hud` | `FrpgMenuDlgFeShortcut` (bottom-left equipment slot block). Hook `hud_update0` runs `lock_apply()` + `cam_apply()` (once per gameplay frame on the game thread), the original Update (`0x140676dc0`), then hides the block. | Off: `dsr_stockhud`, or no `dsr_assets/items.json`. Then lock/cam do not run either. |
| `0x1413a8958` (+0x80 = `0x1413a89d8`) | .rdata vtable | W slot 16 | Agent `hud.c:hook_hud` | `FrpgMenuDlgShortcutItem` (quick item select popup). Hidden after the original Update (`0x1406581e0`). | Same flags. |
| `0x1413b1b68` (+0x80 = `0x1413b1be8`) | .rdata vtable | W slot 16 | Agent `hud.c:hook_hud` | `FrpgMenuDlgMapAction` ("Pick up item" / "Talk" prompt box). Hidden after the original Update (`0x1406802b0`). The app's Interact pill shows the text instead. | Same flags. |
| `0x1413b5b10` (+0x80 = `0x1413b5b90`) | .rdata vtable | W slot 16 | Agent `title.c:hook_title` | `FrpgMenuDlgTitle`. Hook `title_update` publishes the dialog address and moves the highlight on a tap (section 5). Original `0x140693280`. | Always on (no flag). |
| dialog `+0x18` | heap | R | Agent `hud.c:hide_objects` | Pointer to the dialog's object list. | |
| dialog `+0x20` | heap | R | Agent `hud.c:hide_objects` | Object count (u32). Agent skips if > 256. | |
| object `+0x28` bit 1 (0x02) | heap | W (clear) | Agent `hud.c:hide_objects` | Visible bit. Cleared after each Update = object not drawn. | Overhaul UIFeatures trick. Does not hide `FrpgMenuDlgObjItemSelect` (vt `0x1413a85f0`, quick-item name line; sub-elements 0x50 bytes from +0x48, vt `0x1414f6988`). Kept on purpose. Clearing the bit on the HP/stamina HUD dialogs did nothing (2026-10-15). |

## 3. MenuMan (`[0x141c88d98]`)

### 3.1 State array

`MenuMan + 0x30` holds `int state[500]`. Slot `id` is at **`MenuMan + 0x30 + 4*id`**. The game reads it with `GetState 0x14071abd0` and writes it with `SetState 0x14071abf0`. A slot is a small state machine: 0 = closed, other values are menu specific. Full owner list: `re/ui/menu_ids.txt`.

| id | Offset | R/W | Who | Meaning (values) |
|---|---|---|---|---|
| any 0..499 | +0x30..+0x7ec | R/W | Agent `ui.c:ui_command` (`set ID V`, `get ID`), `ui_log_state_diff` (`statelog 1`) | Debug channel through `dsr_cmd.txt`. |
| 2 | +0x38 | R; W 1 | App `poll` (≠0 = INVENTORY); Agent `ui.c` `tab 0` | Inventory. 1 = open request, 0 = closed. |
| 3 | +0x3c | R; W 10 | App `poll` (≠0 = EQUIPMENT); Agent `ui.c` `tab 1` | Equipment. 10 = open request, 11-19 sub-states. |
| 8 | +0x50 | R; W 7 / 2 | App `poll` (≠0 = MENU, ==8 = BAR); Agent `hud.c:menu_hud` (≠0 = menu), `ui.c` `menubar` (W 7), `tab` (needs 8, then W 2) | Menu bar (StartTab). 0 closed, 7 open request, 8 bar open idle, 2 sub-menu opened from bar, 1/3/6 closing, 4/5 transitions. Option pages clear it when opened from System. |
| 9 | +0x54 | R | App `poll` (2 = BONFIRE screen, 4 = `talking`); Agent `hud.c:menu_hud` (≠0 and ≠4 = menu) | Talk-ESD menus: 2 = bonfire list, 4 = NPC conversation, 0 = none. Goes 2 → 0 when a bonfire sub-screen (Level Up) opens. |
| 0x11 | +0x74 | R | App `poll` (startup notice: ==1 on bare title; title sub-screen: ≠0) | General dialog (`FrpgMenuDlgGeneral`, yes/no, message box R09-00). Game test `IsGeneralIdle 0x140681ea0`. |
| 0x13 | +0x7c | R | App `poll`; Agent `hud.c:menu_hud` | EnvOption (Options page). 0 and 5 = closed (5 stays after PC settings closes). |
| 0x14 | +0x80 | R | App `poll` (==1 = TITLE) | Title menu active (1 = title shown). The app reads it as "MenuMan+0x80". |
| 0x15 | +0x84 | R; W 1 | App `poll` (≠0 = STATUS); Agent `ui.c` `tab 2` | In-game Status. 1 = open. |
| 0xb2 | +0x2f8 | R | App `poll` (title sub-screen / option page, ≠0 and ≠5); Agent `hud.c:menu_hud` | Network settings (FrpgMenuDlgNetworkOption). 2 = open; 0 and 5 = closed (like 0xb1 PC settings). DRB R16 (6 rows) / R17 (5 rows). |
| 0x17 | +0x8c | R | App `poll` (≠0 = LEVEL_UP); Agent `hud.c:menu_hud` (≠0 = menu) | Level Up screen (from the bonfire). 1 = opening, 2 = open (statelog 2026-10-16). |
| 0x19, 0x1a, 0xb, 0xc, 0xd, 0x40, 0x24 | +0x94, +0x98, +0x5c, +0x60, +0x64, +0x130, +0xc0 | R | App `poll` (`STATION_IDS`, ≠0 = MENU, screen OTHER); Agent `hud.c:menu_hud` (≠0 = menu) | Station menus: attune magic, bottomless box, buy shop, repair, upgrade, sell shop, warp (`re/ui/menu_ids.txt`). Attune: 0x9 2 → 0, 0x19 0 → 1 → 2 (statelog 2026-10-16). |
| 0x1d | +0xa4 | R | App `poll` (title sub-screen, notice check) | Saved-characters list (Load Game / Delete). 3 reload, 4 browsing, 5 load, 6 delete, 0 closed. |
| 0x1e | +0xa8 | R | App `poll` (`charMakeStep`), `dsrCharMakeWatch` | Character creation sub-step: 2 browsing, 5 "Enter character name" box (app presses OK), 7 typing the name (app opens the keyboard). (statelog 2026-10-16) |
| 0x25 | +0xc4 | R | App `poll` | Face edit (character creation). |
| 0x27 | +0xcc | R | App `poll` | Class select (`FrpgMenuDlgSelectArchitype`). |
| 0x26 | +0xc8 | R | App `poll` (≠0 = CHAR_MAKE) | Character creation main screen (New Game). Stays 1 during the opening movie. Also 1 on the boot logo screens (with 0x3c = 1), so the app needs 0x1e ≠ 0 too. |
| 0x29 | +0xd4 | R | App `poll` (≠0 = movie → Skip layer) | Bink movie playing (opening after character creation; 0x54 = 1 and 0x5b = 9 at the same time). |
| 0x2a | +0xd8 | R; W 1 | App `poll` (≠0 = SYSTEM); Agent `hud.c:menu_hud` (==3 = decide step → HUD on), `ui.c` `tab 3` | System menu. 1 = open, 3 = decide step (a page is about to open). |
| 0x3b | +0x11c | R | App `poll` (OPTIONS); Agent `hud.c:menu_hud` | DispOption (Display page). |
| 0x42 | +0x138 | R | App `poll` (OPTIONS); Agent `hud.c:menu_hud` | SoundOption (Sound page). |
| 0x4b | +0x15c | W 0-3 | Agent `ui.c` `tab N` | Menu bar selected tab: 0 Inventory, 1 Equipment, 2 Status, 3 System. |
| 0x75 | +0x204 | W 0 | Agent `ui.c` `tab 0` | Inventory sub-state (game resets it to 0 on open). |
| 0x7d | +0x224 | W 1 | Agent `ui.c` `menubar` | Menu bar "busy" flag. Game opens the bar with state[0x7d]=1, state[8]=7. |
| 0x88 | +0x250 | W 1 | Agent `ui.c` `closeall` | Close-all request. StartTab update closes all menus. |
| 0xb1 | +0x2f4 | R | App `poll` (OPTIONS); Agent `hud.c:menu_hud` | PcOption (PC settings page). 0 and 5 = closed. |

Phase logic in the app (`DsrGameState.poll`):
- `state[0x14] == 1` → TITLE. Title sub-screen (Back useful) if any of 0x1d, 0x2a, 0x13, 0x3b, 0x42, 0x25, 0x27, 0x11 ≠ 0.
- Startup notice: TITLE, all of 0x1d, 0x2a, 0x13, 0x3b, 0x42, 0x25, 0x27 = 0, and `state[0x11] == 1`. The app presses A. The agent now removes the notice (section 9), so this rarely fires.
- `state[8] ≠ 0` or an option page open (0x13/0xb1 not 0 or 5; 0x3b or 0x42 ≠ 0) → MENU. Screen order: 2, 3, option page, 0x15, 0x2a, `state[8] == 8` (BAR), else OTHER.

### 3.2 Other MenuMan fields

| Offset | R/W | Who | Meaning |
|---|---|---|---|
| +0x81c (i32) | R | App `poll` | Item-get popup item id. -1 = none. ≠ -1 → app keeps the Interact pill up (`actionPrompt = 1`). |
| +0x828 (i32) | R | App `poll`, `DsrAssets` (prompts.json lookup) | Map-action prompt id (Event_text_ id, e.g. 10010103 = "Pick up item"). > 0 while the game offers an interaction. `FrpgMenuDlgMapAction` Update `0x1406802b0` shows it. |

## 4. GameDataMan (`[0x141c8a530]`) and player data

| Path | R/W | Who | What it does / what changing it does | Notes |
|---|---|---|---|---|
| `GDM+0xa4` (u32) | R | Agent `governor`, `trace_igt` (guard page on its page, unused); App `poll` | In-game time, ms. `IGT += (int)(tick*1000)` once per logic tick (`0x140758c5e`). Stops on loading screens. | App: no change for 300 ms = LOADING. Governor: ΔIGT = ticks run. |
| `[GDM+0x58]+0x11` (u8) | R/W | Agent `hud.c:menu_hud` (2 ms thread) | HUD option (1 on, 0 off). Agent writes 0 while the menu bar/tabs, Display or Sound pages are open; 1 everywhere else (incl. System decide step, Options, PC settings). | Locked ON since 2026-10-15 20:05. Off: `dsr_menuhud`. |
| `[GDM+0x68]+0xc4` (i32) | W 2 | Agent `display.c:pin_display` (once) | PC display option: screen mode. 2 = borderless at desktop size. | Off: `dsr_keepdisplay`. |
| `[GDM+0x68]+0xd0 / +0xd4` | W | same | Window W / H = `GetSystemMetrics(SM_CX/CYSCREEN)`. | Stops a saved 16:9 size from adding black bars. |
| `[GDM+0x68]+0xd8 / +0xdc` | W | same | Fullscreen W / H = screen size. | |
| `GDM+0x10` | R | App `poll` | `PlayerGameData*` (PGD). | |
| `PGD+0x30c / +0x310` (i32) | R | App `readLoadout` | Left / right hand selector (0 slot 1, 1 slot 2). | |
| `PGD+0x324 + 8*L` / `PGD+0x324 + 8*R + 4` | R | App `readLoadout` | Equipped left / right weapon item id. | Slot array: 0 L1, 1 R1, 2 L2, 3 R2 … |
| `PGD+0x418` → `+0x78` | R | App `readLoadout` | Magic data ptr → selected spell slot (0..11). | |
| `[PGD+0x418]+0x18 + 8*s` / `+0x1c + 8*s` | R | App `readLoadout` | Attuned spell id / casts left. | |
| `PGD+0x3d8` | R | App `readLoadout` | Inventory list ptr. Entry 0x1c bytes: +4 item id, +8 quantity. | |
| `PGD+0x44c` (i32) | R | App `readLoadout` | Selected quick item → inventory index (0..2047). | |
| `PGD+0x438 + 4*i`, i<5 | R | App `poll` (`quickSlots`) | Quick bar → inventory index (-1 empty). | |
| `[0x141c77e50]+0x68` → `ChrIns+0xb20` (i32) | R | App `readLoadout` | Player two-hand style: 1 one-handed, 3 right 2H, 2 left 2H. | Found by ChrIns diff. |

## 5. Title screen

| Address / offset | Section | R/W | Who | What it does / what changing it does | Notes |
|---|---|---|---|---|---|
| `0x141a32250` | .data table | W | Agent `title.c:patch_title_list` (DllMain) | 10 title entries × 12 bytes `{text id, action, command}`. Agent finds `{0x61f9a "Log In", action 5}` (entry 5) and sets action = 7. The game always filters actions 7/8, so the list has 5 entries and uses no-scroll mode (entry i in slot i). | List builder `0x1406940c0`. Off: `dsr_stocktitle`. |
| `0x1412f6154` (y of `{960, 540}` at `0x1412f6150`) | .rdata float | W | Agent `title.c:patch_title_list` | Title logo centre y in 1920×1080 space. 540 → 400 = logo higher, clear of the one-row menu. | Read only by `0x14025bcf0`, `0x14025c2a0`. Only if value is 540. Off: `dsr_stocktitle`. |
| heap UTF-16 `"PRESS ANY BUTTON"` | heap (FMG) | W | Agent `title.c:replace_title_text` | Overwritten in place with `"TOUCH TO START"`. FMG Menu_others_ 130008 / System_message_win32_ 101000, several copies. | Scans every 2 s, up to 2 min. Skips the image range. Off: `dsr_stocktitle`. |
| TitleDlg `+0x234` (i32) | heap | W | Agent `title.c:title_update` | Highlighted slot = entry index in no-scroll mode. Agent sets it to the tapped entry, then writes `dsr_title_ack.txt`; the app presses A. | |
| TitleDlg `+0x244` (i32) | heap | R | Agent `title_update` | Entry count. Pick must be < count. | |
| TitleDlg `+0x24d` (u8) | heap | R | Agent `title_update` | Scroll mode (0 = no scroll). Pick rejected if ≠ 0. | |
| TitleDlg `+0x254 / +0x255` (u8) | heap | R | Agent `title_update`; App `titleListShown` (reads i32 at +0x254, `& 0xffff == 0x0101`) | Both 1 = main-menu list shown and taking input. Both 0 on "TOUCH TO START". | Agent publishes the dialog address in `dsr_title_dlg.txt`. Picks older than 6 s are dropped. |

### 5.1 Title version lines

| Address | Section | R/W | Who | What | Notes |
|---|---|---|---|---|---|
| `0x141c84c58` | .data `std::wstring` | R/W | Agent `title.c:patch_version_text` | App version (stock L"1.03.1"). +0 allocator, +8 inline buffer or heap ptr, +0x18 size, +0x20 capacity (inline when < 8). Set to L"1.03.1-mobile". | Shown after FMG 401320 "App ver." by the title builder 0x1406935f8. |
| `0x141c84c88` | .data `std::wstring` | R/W | same | Regulation version (stock L" 1.04"). Set to L" 1.04
Modder: kbRadu". | After FMG 401322 "Regulation ver.". DRB `info_versionReg` is 2 lines tall, line spacing byte +0x12 = 36. |
| `0x1400bd1b0` | .text fn | call | same | Game's `wstring::assign(this, ptr, len)`: the longer text is allocated by the game's allocator (freed normally at exit). | Called once from the agent thread when both strings hold the stock text. Off: `dsr_stockver`. |

## 6. Fonts

| Address | Section | R/W | Who | What it does / what changing it does | Notes |
|---|---|---|---|---|---|
| `0x1413d3950` | .rdata table | – | Agent `title.c:patch_fonts` (base) | Font preset table: 13 × 0x18 `{name, fontId, baseSize 24, scaleX +0x10, scaleY +0x14}`. DRB Text byte +0x1c selects the index. Read at every text Begin, never copied. | `docs/ui/FONTS_RE.md`. |
| `0x1413d3978 / 0x1413d397c` (idx 1 scaleX/Y) | .rdata float | W | Agent `patch_fonts` (DllMain) | Preset 1 (stock 16 pt, 0.5) → 2.0. Used by System list and item command menu after `patch_menu.py` FONT_BUMPS. | Off: `dsr_stockfont`. |
| `0x1413d3990 / 0x1413d3994` (idx 2 scaleX/Y) | .rdata float | W | Agent `patch_fonts` | Preset 2 (stock 18 pt, 0.583) → 1.4. Used by Options, PC settings, Key settings, message boxes. | Off: `dsr_stockfont`. |

## 7. Camera

| Path | R/W | Who | What it does / what changing it does | Notes |
|---|---|---|---|---|
| `[0x141c7a488]+0x60` → `+0x60` | R | Agent `cam.c:follow_cam` | ChrExFollowCam object (vt `0x1412eefd8`). | |
| FollowCam `+0x1fc .. +0x228` (12 floats) | R/W | Agent `cam.c:cam_apply` (game thread, per frame) | Yaw/pitch speed pairs (base, max, acceleration). Agent multiplies each by 1.5 (`CAM_SPEED`). Stock: yaw base 120 °/s, max 260 °/s. Re-applied when the game resets a value to stock. | Update code `0x14023704a`. Only when `f[0]` is in (0.1, 20]. Off: `dsr_stockcam`. |
| FollowCam `+0x144` yaw, `+0x140` pitch | – | (not used) | Direct writes do not hold: the update recomputes them each frame. | Documented in `cam.c` only. |
| `[LockTgtMan+0x1438]+0x10 .. +0x5f` | R | App `readLockScan` | ChrCam: world matrix (16 floats, row 3 = position), then fovY, aspect, near, far. App inverts it to project lock candidates. | `docs/LOCKON.md` §2. |
| `[0x141b68ec8]+0x6f0 / +0x6f4` | R | App `readLockScan` | Render width / height (float) for the projection. | |

## 8. Lock-on (`LockTgtManImp`, `[0x141c7a138]`)

| Offset | R/W | Who | What it does / what changing it does | Notes |
|---|---|---|---|---|
| `+0x10` | R | Agent `lock.c:lock_apply`; App `readLockScan` | First candidate entry. Entries linked by entry `+0x30`. Max 64 walked. | |
| entry `+0x00/+0x04/+0x08` | R | App `readLockScan` | Lock-point world x, y, z. | |
| entry `+0x30` | R | both | Next entry. | |
| entry `+0x38` | R | both | Lock point ptr. Key of the pick (with the handle). | |
| entry `+0x40` (u8 flags) | R/W | App R; Agent W | 0x10 lockable now, 0x20 current target, 0x40 LOS blocked. Agent clears 0x20 on all entries, sets it on the pick. Eligible pick: `(flags & 0x50) == 0x10`, or 0x20. | Same as the stick-flick switch `0x14040c2c0`. |
| lock point `+0x14` (u32) | R | both | Owner ChrIns handle. | |
| `+0x1430` (u8) | R | App `readLockScan` | Locked now. | App: tap on locked target or empty space = unlock. |
| `+0x1431` (u8) | W | Agent `lock_apply` | Lock request. 1 = lock (with the 0x20 flag moved), 0 = unlock. | Runs on the game thread from the FeShortcut hook. |
| `+0x1438` | R | App `readLockScan` | ChrCam ptr (section 7). | |
| `+0x1440` (float) | W 0.5 | Agent `lock_apply` | Target-switch cooldown, same as the stick switch. | |
| `+0x156b` (u8) | R | Agent `lock_apply` | Lock-on allowed now (0 in cut-scenes / menus → request ignored). | |

## 9. Offline notice handlers

"Game will start in offline mode." (text id `0xc545`, System_message_win32_ FMG) is shown by two title state handlers. Static init stores each handler pointer in `.data`. The agent swaps the pointers (not the code).

| Address | Section | R/W | Who | What it does / what changing it does | Notes |
|---|---|---|---|---|---|
| `0x141c715c8` | .data fn ptr | R/W | Agent `title.c:patch_offline_notice` | Holds `0x14028a720` (show notice, then state 0xc). Replaced by `notice_skip1`: `self+0x10 = 0xc` (go on without the dialog). | Filled by static init `0x140013d70`. Swapped only when it holds the original. Off: `dsr_offlinenotice`. |
| `0x141c8b278` | .data fn ptr | R/W | same | Holds `0x140804c60` (show notice, then state 0x40). Replaced by `notice_skip2`: `self+0xc0 = 1` (OK result), `self+0x10 = 0xa`. | Filled by `0x140037548`. |
| handler `self+0x10` (i32) | heap | W | `notice_skip1/2` | Title step state. | |
| handler `self+0xc0` (i32) | heap | W | `notice_skip2` | Dialog result (1 = OK). | |

## 10. Input

| Address / offset | Section | R/W | Who | What it does / what changing it does | Notes |
|---|---|---|---|---|---|
| `PadMan+0x68` (u8) | heap | W | Agent `ui.c:ui_mouse_mode` (`mouse 0|1`, `tap X Y`) | KB/mouse mode. MouseMan updates the cursor only when ≠ 0. | Debug / adb channel. |
| exe IAT `USER32!GetAsyncKeyState` | .idata | W | Agent `dinput8.c:hook_input` | Served from a key table refreshed at 20 Hz. The game polls 236 keys per frame (`0x140ca06d9`). | Always on. |
| exe IAT `USER32!SystemParametersInfoA` | .idata | W | Agent `hook_input` | SPI_GETMOUSE from cache, SPI_SETMOUSE dropped (called every frame at `0x140ca1006`). | Always on. |
| exe IAT `USER32!GetCursorPos`, `ScreenToClient` | .idata | W | Agent `ui.c:ui_mouse_hooks` (first `tap`) | Return the tap point (client px). | Debug only. |
| DIMOUSESTATE bytes 0-7, byte 12 | DI buffer | W | Agent `ui.c:ui_di_mouse_patch` | During a tap: X/Y delta 0, left button held for 120 ms. | |
| Wine DirectInput vtables: slot 3 `CreateDevice`, device slots 2 `Release`, 9 `GetDeviceState`, 25 `Poll` | Wine DLL (not the exe) | W | Agent `DirectInput8Create`, `hook_createdev` | Device state served from a cache polled at 100 Hz (mouse deltas summed). | Off: `dsr_nodicache`. |
| exe IAT `KERNEL32!CreateEventW`, `CloseHandle` | .idata | W | Agent `hook_events` | Unnamed manual-reset events reused from a pool (`0x140ccb9c7` creates one per request). | Off: `dsr_nopool`. |
| exe IAT `USER32!CreateWindowExW`, `SetWindowLongPtrW`, `AdjustWindowRect` | .idata | W | Agent `display.c:hook_window` (DllMain) | Strip caption/border bits → `WS_POPUP`; no frame. Stops Wine's title-bar strip. | Off: `dsr_keepdisplay`. |

## 11. Frame pacing / speed / CPU

| Address / offset | Section | R/W | Who | What it does / what changing it does | Notes |
|---|---|---|---|---|---|
| `0x1412ccc78` (float) | .rdata | W | Agent `patch_tick` (1/60 → 1/30, page left RW), `governor` (every 0.5 s), agent loop (`= 1/30` when governor off) | Logic tick length. Read once per frame at `0x14015cec9`, passed to every system. Governor: tick = real s / (ΔIGT / tick ms), EMA 0.5, clamp [1/60, 1/10] → game speed tracks real time. | Governor off: `dsr_nogov` (re-checked every 1 s). |
| heap `FrpgFlipper` object `{vtable, flag byte}` (16 B) | heap | W vtable | Agent `flip_chunk` / `swap_flipper` (scan every 1 s until found, then every 10 s) | Objects whose vtable is `0x1412ab268` (FrpgFlipper_60FPS) get a new vtable: default `0x1412ea790` (30FPS_NoSkip, 1 logic tick per render). | `dsr_skip` → `0x1412ea688` (30FPS, skips render). `dsr_vt.go` → agent copy of the 30FPS vtable with logging slots 3 / 9. Note: a code comment says the pacer swap is off, but the agent loop still calls `swap_flipper()`. |
| `0x1412ab268` | .rdata vtable | R (match) | Agent `flip_chunk` | FrpgFlipper_60FPS (stock pacer). | |
| `0x1412ea688` | .rdata vtable | R | Agent `flip_chunk`, `my_slot3/my_slot9` | FrpgFlipper_30FPS. Slot 3 / slot 9 called by the logging wrapper. | |
| `0x1412ea790` | .rdata vtable | R | Agent `flip_chunk` | FrpgFlipper_30FPS_NoSkip (default target). | |
| `0x1412ea400` (+0x20 mode, +0x28 flipper ptr) | .rdata vtable / heap | R | Agent `report_chunk` (not called) | Pacer manager task. Mode 4 = 60FPS; game re-applies it every frame. | `report()` is dead code: it can crash on false matches. |
| `[0x141c77e88]+0x2c` (i32) | heap | W 4 | Agent `apply_lod` (every 1 s) | Characters updated at full rate (by distance). Stock 10. | `dsr_lod.txt` = "full near dist"; "-1 0 0" = stock. |
| `[0x141c77e88]+0x30` (i32) | heap | W 8 | same | Characters counted as near; other off-screen ones get interval 5. Code comment: stock 20 (RE_NOTES lists 20 too). | |
| `[0x141c77e88]+0x34` (float) | heap | W 25.0 | same | Distance (m) for interval 5 vs 30 of inactive characters. Stock 40. | Effect: `0x14036e8d0` sets `chr+0x164` = update interval. |
| `GDM+0xa4` page | heap | guard page | Agent `trace_igt` (dead code) | RE tool: one-shot PAGE_GUARD → stack trace of the IGT writer. | |
| flipper object page | heap | guard page | Agent `trace_flip` | RE tool: logs calls in `0x140204c80-0x140204d30` (30FPS slots). | Only with `dsr_flip.go`. |
| main thread | – | suspend/unwind | Agent `profile` | Sampling profiler → `dsr_prof.txt`. | Only with `dsr_prof.go` (seconds). |

## 12. Save file offsets (`DRAKS0005.sl2`, file on disk)

| Offset | R/W | Who | Meaning |
|---|---|---|---|
| file `+0x20` (i64) | R | App `DsrLauncher.clearQuitFlag` | BND4 entry-header size. |
| `0x40 + 10*hdr` | R | same | Entry 10 header (system data). `+8` size (i64), `+0x10` data offset (i32). |
| data `+0 .. +0x0f` | W | same | MD5 of data `+0x10 .. size` (recomputed). |
| data `+0x10 .. +0x1f` | R | same | AES IV. |
| data `+0x20 ..` | R/W | same | AES-128-CBC ciphertext, key `0123456789ABCDEFFEDCBA9876543210`. |
| plaintext `+0x1068` (u8) | W 0 | same | "Not closed with Quit Game" flag. Android kills the game, so the app clears it before launch. |

The app also edits `DarkSouls.ini` (`DsrLauncher.writeDisplayIni`): `[DisplaySetting] WindowMode=2`, Width/Height in `[DisplaySettingWindow]` / `[DisplaySettingFullScreen]`, and `Blur`, `Antialiasing`, `DOF`, `AmbientOcclusion` = 0 in `[DisplaySettingFilter]`.

## 13. Read-only code references (RE and logging only)

These `.text` addresses are named in the code. The agent never writes them.

| Address | Who | Meaning |
|---|---|---|
| `0x14015cec9` | `dinput8.c` comment | Per-frame load of the tick constant. |
| `0x140758a30-0x140758c98`, `0x140758c5e` | `dinput8.c:veh` | IGT update function; `IGT += tick ms`. |
| `0x140204c80-0x140204d30` | `dinput8.c:veh` | FrpgFlipper_30FPS slot code (trace range). |
| `0x140001000-0x142000000` / `0x143000000` | `dinput8.c:veh` | Return-address filter for stack logs. |
| `0x140ca06d9`, `0x140ca1006`, `0x140ccb9c7` | `dinput8.c` comments | GetAsyncKeyState loop, SPI call, CreateEventW caller. |
| `0x14036e8d0` | `dinput8.c:apply_lod` comment | Sets `chr+0x164` (update interval 0/2/5/30). |
| `0x14040c2c0` | `lock.c` comment | Stick-flick target switch (model for tap-to-lock). |
| `0x14023704a` | `cam.c` comment | ChrExFollowCam update (speed math). |
| `0x1406940c0` | `title.c` comment | Title list builder. |
| `0x14025bcf0`, `0x14025c2a0` | `title.c` comment | Title logo draw functions. |
| `0x140686bc0`, `0x140686c20`, `0x140686f30` | `title.c` comment | General dialog init / set text / show. |
| `0x14028a720`, `0x14028a810`, `0x140804c60`, `0x140804cc2` | `title.c` (originals compared) | Offline-notice state handlers. |
| `0x140681ea0` | `title.c` comment | MenuMan state 0x11 free (general dialog idle). |
| `0x140013d70`, `0x140037548` | `title.c` comment | Static init that fills the two handler slots. |
| `0x1406802b0` | `DsrGameState.kt` comment | FrpgMenuDlgMapAction Update. |
| `0x1413a85f0`, `0x1414f6988` | `hud.c` comment | ObjItemSelect vtable, its sub-element vtable. |

## 14. Unclear writes

| Address | Section | R/W | Who | Meaning |
|---|---|---|---|---|
| `0x141a32779` (u8) | .data | W 1 | Agent `ui.c` `tab 3` | Unknown. The game's System-open function `0x1406f3240` also sets it; the agent copies that. |

## 15. Menu layout file (`menu/menu.drb.dcx`, not memory)

`tools/patch_menu.py` edits DRB shape params (rect i16×4, scaling origin, scaling type, Text +0x1c font, +0x1e alignment, Sprite +0x20 colour). Dialogs it changes:

| Dialog(s) | Change |
|---|---|
| `F20-00` (HUD root), `soul_param` | Quick-item name under the app's Estus slot; souls box under HP/stamina; HP/stamina group, humanity ring, status / broken icons shifted. |
| `T00-00` (title) | 5 entries in one row, font 11, 72 units high; scroll arrows and fade masks off-screen. |
| `I06-00`, `I06`, `I06_parchment6r/5r/4r`, `I06_frame_big*` (System list) | Scaled x1.15 / y2.3, font 7→1, Key settings row hidden, rows moved up, frame trimmed one row. |
| `I01`, `I01-01` (item command menu), `I01_tab_arrow` | Scaled x1.5 / y2.0, rows 65 units, font 8→1, divider hidden; type-strip arrows invisible. |
| `R00`, `R00-00`, `*_category_name` (tab strip) | Frame, help, arrows, cursor off-screen; icons invisible but kept as click targets. |
| `R01`, `R01-00`, `R01_parame_plate`, `R01_parchment` (Options) | Two columns of 7 rows, fonts 7→2 / 9→1, labels and dividers hidden. |
| `R14-00`, `R14-01`, `R14_parchment` (PC settings) | One column, 58-unit rows, fonts 7→2 / 9→1. |
| `R13`, `R15` (+ parchments) (Key settings) | x1.1, font 6→2. |
| `R09-00` (general message box) | Buttons 80 units high, font preset 2, box taller. |
| `F05-00` (question box, "Quit game?") | Buttons 80 units high, font preset 2, divider hidden. |
| all dialogs | Objects with scaling origin (1280, 0) → (640, 0) (centred); `text_key-guide*` off-screen. |

### 15.1 Splash textures (`menu/menu_2.tpf.dcx`, file on disk)

| Item | File | What | Who |
|---|---|---|---|
| `Logo_02` | `menu/menu_2.tpf.dcx` | Bandai Namco splash, DXT1 4096x2048, stock on white. Recoloured in place: background → black, white letters kept. | `tools/dark_splash.py` → `tools/out/menu_2.tpf.dcx` (pushed by `batch_test.sh`) |
| `logo_BNG` `object1..4` | `menu/menu.drb.dcx` | White MonoRects around the splash (22:9 side bars). Colour RGBA at shape +0x18 → black. | `patch_menu.py` `MONO_COLOR` |
| `Logo_01` / `Logo_03` / `Logo_04` | `menu_2` / `menu_4` | FromSoftware, Havok and the DSR title art: already on black. | none |

## 16. Flag files (game folder)

Create the file to switch the patch off (unless noted).

| File | Effect | Read by |
|---|---|---|
| `dsr_noagent` | Plain proxy: no hooks, no patches, no agent thread. | `dinput8.c:DllMain` |
| `dsr_nodicache` | No DirectInput state cache. | `hook_createdev` |
| `dsr_nopool` | No event pool (CreateEventW / CloseHandle hooks). | `hook_events` |
| `dsr_nogov` | No speed governor; tick fixed at 1/30. | agent loop |
| `dsr_stockver` | Keep the stock title version lines. | `title.c:patch_version_text` |
| `dsr_skip` | Pacer swap uses FrpgFlipper_30FPS instead of 30FPS_NoSkip. | `flip_chunk` |
| `dsr_vt.go` | Pacer swap uses the logging vtable copy. | `flip_chunk` |
| `dsr_flip.go` | Turns ON the flipper guard-page trace. | agent loop |
| `dsr_prof.go` | Turns ON the profiler (content = seconds; file deleted). | `check_profile` |
| `dsr_lod.txt` | LOD values "full near dist"; "-1 0 0" = stock. | `apply_lod` |
| `dsr_stockhud` | Keep the stock FeShortcut / ShortcutItem / MapAction HUD (also disables tap-to-lock and camera speed: they run from that hook). | `hook_hud` |
| `dsr_assets/items.json` (missing) | Same as `dsr_stockhud`. | `hook_hud` |
| `dsr_menuhud` | Leave the HUD option byte alone. | `menu_hud` |
| `dsr_stocktitle` | Keep the title list, logo position and "PRESS ANY BUTTON". | `title.c` |
| `dsr_stockfont` | Keep font presets 1 / 2. | `patch_fonts` |
| `dsr_offlinenotice` | Keep the offline notice handlers. | `patch_offline_notice` |
| `dsr_stockcam` | Stock camera speed. | `cam_apply` |
| `dsr_keepdisplay` | No display-option pin, no window-style hooks. | `pin_display`, `hook_window` |

IPC files (not switches): `dsr_cmd.txt` (debug commands), `dsr_lock.txt` (tap-to-lock request), `dsr_title.txt` / `dsr_title_ack.txt` (title tap), `dsr_title_dlg.txt` (title dialog address), `dsr_agent.log`, `dsr_prof.txt`.
