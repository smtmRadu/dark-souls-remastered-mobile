# DSR menu / UI reverse engineering (exe 1.03.1, base 0x140000000)

Static analysis only. Nothing here ran in the game yet.
Confidence: **S** = seen in disassembly/decompile, **C** = also in community source (Overhaul, DSR-Gadget, SoulSplitter), **G** = guess. **RT** = needs a runtime check (see the last section).

Tools (all in `re/ui/`):
- `dsr.py`: pefile/capstone/numpy helpers: `.pdata` bounds, `root()` (follows chained unwind), `rip_refs()`, `calls_to()`.
- `rtti.py`: RTTI class → vtable dump (`rtti_all.tsv`, UI subset in `rtti_ui.txt`).
- `ctors.py Class...`: vtable, slots, code that references the vtable (ctor/dtor).
- `fields.py GLOBAL`: every `[global]+disp` access (R/W, size), used for MenuMan, MouseMan, PadMan, LockTgtMan.
- `menuids.py`: all 1794 calls of MenuMan `GetState/SetState` with constant id/value, plus owning dialog class (`menu_ids.txt`).
- `leafs.py`: splits a code range at int3 padding (finds leaf accessors that have no `.pdata`).
- `ghidra/dec.sh <addrs> <out.c>`: no-analysis Ghidra decompile (own project `re/ui/ghidra/uiproj`, about 25 s per batch). Labels come from `ghidra/symbols.txt`. Decompiles are in `ghidra/out*.c`.

## 1. Menu system

### 1.1 Main objects
| Address | Meaning | How found | Conf |
|---|---|---|---|
| `0x141c88d98` | `MenuMan*` (RTTI `MenuMan`, vtable `0x1413d08e0`, ctor `0x140719cc0`) | Overhaul + RTTI + 192 rip refs, all inside `0x14071a000-0x14071d440` (MenuMan accessors) | S C |
| `0x14071ab90` | `Step_MenuMan_And_MouseMan(dt)`: calls `MenuMan::Update 0x14071a280`, then `MouseMan::Update 0x1401b72d0` | Overhaul name + disasm | S C |
| `0x141c6aed8` | `FrpgMouseManImp*` (vtable `0x1412dff40`, ctor `0x1401b7220`), created in `0x14071a690` | store after ctor call | S |
| `0x1402879c0` | `InGameMenuStep::StepAllMenus`: steps each `FrpgMenuSys*` held at InGameMenuStep `+0x98,+0xa8,+0xb0,+0xe0,+0xe8,+0x138,+0x160,+0x168,+0x180,...` | disasm | S C |
| `0x140716690` | `FrpgMenuSys::Step(sys, dt, flag)`: pad input → `0x140edc050`; mouse input → `0x140716810`; then dialog update `0x140ee17b0` | decompile | S |
| `0x14024f6b0` | `InGameStep::Update` (Overhaul `MoveMapStep_Step_13`). Opens the menu bar on Start and drives lock-on toggle, camera and HUD projections | decompile | S |

### 1.2 MenuMan layout
The core is an `int state[500]` array at `MenuMan+0x30`. Each menu (dialog) owns one or more slots. A slot is a small state machine: 0 = closed; other values are menu specific.
- `GetState(id)` = `0x14071abd0` (`return state[id]`), 680 call sites.
- `SetState(id, v)` = `0x14071abf0` (`if id < 500: state[id] = v`), 1114 call sites.
Offset of slot `id` = `0x30 + 4*id`. The full list (owner class per id) is in `re/ui/menu_ids.txt`.

| MenuMan off | state id | Meaning / values | How found | Conf |
|---|---|---|---|---|
| +0x38 | 2 | Inventory. 1 = open request, 0 = closed, 4/11/14 internal | `0x1406acf00` OpenInventory = `Set(0x75,0)`, then `Set(2,1)` if closed; close = `0x1406ace70` | S |
| +0x3c | 3 | Equipment. 10 = open request (`0x140632280`), 0 closed, 11-19 sub-states | menuids + decompile | S |
| +0x50 | 8 | **Menu bar (StartTab) state**: 0 closed, 7 = open request (InGameStep sets it on Start), 8 = bar open and idle, 2 = a sub-menu opened from the bar, 1/3/6 closing, 4/5 transitions | StartTab update `0x14066ee10` switch. **Corrects RE_NOTES**: +0x50 is not a menu id; 8 and 2 are bar states | S |
| +0x54 | 9 | Talk/msgbox (FrpgMenuDlgTalkMsgbox) | menuids | S |
| +0x74 | 0x11 | General dialog (yes/no etc., FrpgMenuDlgGeneral). `IsGeneralIdle = 0x140681ea0` | menuids | S |
| +0x80 | 0x14 | **Title menu active** (1 = title shown). Set by `0x1406928a0`, cleared by `0x140693a90` when a title command is chosen | Overhaul + decompile | S C |
| +0x84 | 0x15 | In-game Status. 1 = open (`0x1406b0b80`), 0 = close (`0x1406b0ba0`), `IsOpen = 0x1406b0b60` | decompile | S |
| +0x8c | 0x17 | Soul status / level up | menuids | S |
| +0x94 | 0x19 | Magic attune | menuids | S |
| +0xa4 | 0x1d | **Saved-characters list (Load Game / Delete)**. 3 = (re)load list, 4 = browsing, 5 = load chosen slot, 6 = delete chosen slot, 2/7/8/9/10 transitions, 0 closed | Overhaul (3/4) + ProfileSelect decompile | S C |
| +0xc0 | 0x24 | Bonfire warp | menuids | S |
| +0xd8 | 0x2a | System menu. 1 = open (`0x1406f3240`, also sets byte `0x141a32779`), 0 close (`0x1406f31b0`) | decompile | S |
| +0x15c | 0x4b | **Menu bar selected tab**: 0 Inventory, 1 Equipment, 2 Status, 3 System | `0x14066e3f0`, `0x14066f6a0`, table `0x1413ae220` | S |
| +0x194 | 0x59 | **Selected save slot** in the Load list (= list cursor row + scroll top, written each frame by `FrpgMenuDlgProfileSelectList::Update 0x1406a6110`) | decompile | S |
| +0x204 | 0x75 | Inventory sub-state (reset to 0 on open) | `0x1406acf00` | S |
| +0x200 | 0x74 | HUD: PC gauge hide flag (non-zero hides) | PCGauge `0x14067bb20` | S |
| +0x210 | 0x78 | HUD: PC gauge enable (≥1 needed) | PCGauge, setter `0x14071b7f0(cl,dl)` sets +0x210 = cl, +0x200 = dl | S |
| +0x214 | 0x79 | HUD: shortcut slots (FeShortcut) hide. Setter `0x14071b830(cl)` writes `!cl` | disasm | S |
| +0x224 | 0x7d | Menu bar "busy" flag. `0x14071b3c0` = open bar: if state[8]==0 && state[0x7d]==0 then state[0x7d]=1, state[8]=7 | decompile | S |
| +0x24c | 0x87 | System "return to title". Write 2 = quit to main menu | DSR-Gadget `MenuKick` | C |
| +0x250 | 0x88 | **Close-all request**. StartTab update: if non-zero → close all menus (`0x14071b2b0`), reset bar | `0x14066ee10` | S |
| +0x2e4 | 0xad | "Menus/HUD suppressed". Listbox and HUD dialogs skip update when ≠0. InGameStep rewrites it every frame via `0x14071b430` | decompile | S |
| +0x448 | 0x106 | Saved-chars list mode: 0 = load, 1 = delete | `0x1406a3b10/0x1406a3b60` | S |
| +0x44c | 0x107 | Slot to load (copy of state[0x59], written by ProfileSelect update) | `0x1406a4150`, read by LoadGameStep via `0x1406a3c30` | S |
| +0x45c | 0x10b | Load list result: 1 = load confirmed, -1 = cancelled | `0x1406a3bb0/0x1406a3bd0` | S |
| +0xa20 | – | **Lock-on reticle screen pos** `{float x, y, z, w; u8 visible @+0x10}`. Getter `0x14071c7e0`, setter `0x14071c7b0` (called by `0x1406705c0`) | disasm | S |
| +0x908 | – | Floating gauges (phantom HP bars) screen data, 7 × 0x28 bytes. Getter `0x14071c780(i)` | disasm | S |
| +0xa48 | – | Popup message queue (Overhaul `show_popup_message`) | Overhaul | C |
| +0xf80 | – | Banner messages (`Create_BannerMessage 0x14071fc60`) | Overhaul + `0x14071cd50` | S C |
| +0x1110 | – | u8: pad input to menus enabled (`0x14071b150`) | disasm | S |

### 1.3 Menu functions
| Address | Meaning | Conf |
|---|---|---|
| `0x14071ac10` | **`GetOpenMenusMask()`** → u64 bit mask, 0 = no menu open. Bits: 0x1 equipment, 0x2 sell shop, 0x4 blood msg, 0x8 general dialog busy, 0x40 menu bar (state[8]≠0), 0x200 inventory, 0x400000 status, 0x200000 level-up, 0x800000 attune, 0x10000 warp, 0x8000000 system/options, 0x400000000 title, ... | S |
| `0x14071b3c0` | Open menu bar (see state[0x7d]) | S |
| `0x14071b2b0` | Close main menus (bar, inventory, equipment, status, system, options...) | S |
| `0x14071b170(int)` | Close all menus (wider list, 9 callers) | S |
| `0x14071b300(id)` | Switch tab: 2 inv, 3 equip, 0x15 status, 0x2a system; writes state[0x4b] | S |
| `0x14066e3f0(id)` | StartTab: open sub-menu id, close the others | S |
| `0x14066f6a0(this)` | StartTab: "confirm current tab" (open by state[0x4b], then state[8]=2) | S |
| `0x14066f8d0 / 0x14066f920 / 0x14066f940` | Open inventory / equipment / status directly (no direct callers; probably called through a table) | S |
| `0x14066ece0(this, evt, ctrlId)` | StartTab mouse/event handler (vtable slot 35). evt 2 = click on tab button, 8 = hover (sets tab), 6 = right click (cancel) | S |
| `0x140361140` | `ok_to_enter_equipment_menu` | C |
| `0x1406eb370` | `create_popup_window_msg` | C |
| `0x14071fc60` | `Create_BannerMessage(MenuMan+0xf80, type, wstr)` | C |
| `0x14071cd50(id, ...)` | Show banner + set MenuMan+0x108 | S |

### 1.4 Dialog classes (RTTI, vtable)
All in-game windows derive from `FrpgMenuDialog` (vtable `0x1413cfe38`) → `EzMenu::EzMenuDialog`. Menus are data-driven ("EzMenu" scenes + `menuesdbnd` scripts). Full list: `re/ui/rtti_ui.txt`.

| Class | vtable | Role |
|---|---|---|
| FrpgMenuSys | 0x1413d03e8 | One menu system (holds dialogs); stepped by `0x140716690` |
| FrpgMenuDlgStartTab | 0x1413ade30 | Menu bar (Start) |
| FrpgMenuDlgInventory | 0x1413bab78 | Inventory |
| FrpgMenuDlgEquipment / Equip / EquipList | 0x1413a1600 / … | Equipment |
| FrpgMenuDlgIngameStatus | 0x1413bb278 | Status |
| FrpgMenuDlgSystem | 0x1413c8178 | System menu |
| FrpgMenuDlgTitle | 0x1413b5b10 | Title buttons (Continue/Load/New/Options) |
| FrpgMenuDlgProfileSelect / …List | 0x1413b8f88 / 0x1413b9810 | Load Game / Delete list |
| FrpgMenuDlgYesNoMsgbox / General | 0x1413ab888 / … | Confirm boxes |
| FrpgMenuDlgListbox | 0x1413aad28 | Generic list (cursor logic, base of ProfileSelectList etc.) |
| FrpgMenuDlgButtonGroup / CursorGroup / Cursor | 0x1413a9fe0 / 0x1413aa738 / 0x1413aa368 | Buttons and cursor visuals |
| FrpgMenuDlgTargettingSite | 0x1413b14b0 | Lock-on reticle |
| FrpgMenuDlgPCGauge / FEPlayerState / FeShortcut / FEEnemyGauge / BossGauge | 0x1413b06b8 / 0x1413af800 / 0x1413afe10 / … | HUD |

FrpgMenuDialog vtable slots (from base + overrides, S):
| Slot (offset) | Meaning |
|---|---|
| 16 (+0x80) | `Update(this, float dt)` (called by `0x140ee17b0`) |
| 27 (+0xd8) | `SetProperty(this, propId, Variant*)`; Variant = {8-byte value, int type @+8: 1 int, 2 float, 3 ref-counted string} |
| 15 (+0x78) | Get EzMenu scene object |
| 35 (+0x118) | `OnEvent(this, evt, ctrlId, info*)` – mouse/UI events (below) |

Mouse/UI event codes sent to slot 35 by the hit-test object `0x140721db0`: 8 = mouse enter (hover/focus), 9 = leave, 0 = L down, 1 = L up, 2 = **L click (down+up inside)**, 3 = L repeat, 4/5/6 = R down/up/click, 7 = R repeat, 10/11 = wheel up/down, 12 = wheel.
Pad actions are polled with `Dialog::IsAction(this, code)` = `0x140ed6750` (633 callers). Codes seen: 0x85 = decide/confirm, 0x8e/0x8f/0x86/0x87 = up/down (and page), 0x96/0x97 = L/R switch, 0x98/0x99 = page scroll, 0x9b = delete/extra, 0x88-0x91, 0x9a, 0x9d, 0x9e, 0xb4, 0xb5 = menu-bar keys (G for exact mapping).

### 1.5 Cursor / selected item
| Where | Meaning | Conf |
|---|---|---|
| `FrpgMenuDlgListbox +0x214` | cursor row inside the visible page | S |
| `+0x21c` | scroll top (first visible row) | S |
| `+0x208` | visible rows (prop 3000) | S |
| `+0x20c` | columns (prop 0xbb9) | S |
| `+0x218` | total rows = ceil(items / columns) (prop 0xbbb) | S |
| `+0x224 / +0x225` | "scrolled" / "cursor moved" dirty flags | S |
| `+0x23c` | moves done this frame (one move per frame) | S |
| `0x1406612a0(list, up, wrap)` | move cursor one row; `0x140661150(list, up, n)` page scroll | S |
| Selected index | `(top + row) * cols + col` (single column: `top + row`); ProfileSelectList writes `top+row` into state[0x59] | S |
| `FrpgMenuDlgTitle +0x234` | title cursor (button 0..4), `+0x23c` scroll, `+0x210` command table (12-byte entries, command @+8), `+0x250` chosen command, `+0x25c` = 2 to start "decide" animation | S |
| Menu bar | cursor = state[0x4b] | S |

How to set and confirm (options, best first):
1. **Mouse path (native, recommended)**. DSR menus support the mouse. Each frame MouseMan reads `GetCursorPos` + `ScreenToClient` + `GetClientRect`, removes letterbox and scales to the render size (`[[0x141b68ec8]+0x6f0]` float2). Then every FrpgMenuSys hit-tests its controls and sends hover (8) and click (2) events. A tap = move cursor to (x,y), then press and release the left button. A hover already moves the cursor (e.g. menu bar tab, title buttons).
2. **Field write + pad confirm**: write the cursor fields above, then inject a confirm key/button press.
3. **State writes** for menus with a known state slot (open/close/load), no input needed.

### 1.6 MouseMan (`FrpgMouseManImp`, `*0x141c6aed8`)
| Off | Meaning | Conf |
|---|---|---|
| +0x08 | HWND | S |
| +0x10/+0x11/+0x12, +0x14 | Left button: pressed-edge, released-edge, held (u8), hold time (float) | S |
| +0x18..+0x1c | Right button (same layout) | S |
| +0x20..+0x24 | Middle button | S |
| +0x28, +0x2c | cursor x, y (int, render-size pixels, letterbox removed) | S |
| +0x30, +0x34 | previous x, y | S |
| +0x38 | wheel delta (int, from WndProc, cleared next frame) | S |
| +0x40 | u8 "moved this frame" | S |
Position updates only if `PadMan+0x68` (u8, `*0x141c6aea0`) ≠ 0 ("keyboard/mouse mode", `0x1401af690`). Buttons come from the input snapshot `[[0x141b68ec8] + 0x700 + 8*[+0x6f8]]` bytes +8/+9/+10 (L/R/M). That snapshot is filled from the QInput DirectInput mouse (`0x140ca0e80`: `GetDeviceState(0x14)` → `rgbButtons[]`). The keyboard poll `0x140ca06a0` deliberately zeroes GetAsyncKeyState entries 0x10-0x12, so VK_LBUTTON from `GetAsyncKeyState` is not the source (S; RT to confirm).

## 2. Save / Load

| Address | Meaning | How found | Conf |
|---|---|---|---|
| `0x141a32240` | `g_TitleResult`: command chosen on the title. 4 = New Game (NewGameStep), 5 = Load Game (LoadGameStep, continue=0), 0xb = **Continue** (LoadGameStep, continue=1), 7 = PC/game options, 8 = key config, 0xa, 0xd, 9 = other | title flow `0x140804de0` + comparators `0x140692ac0..0x140692c40` | S |
| `0x140693a90` | Title dialog: on decide → `g_TitleResult = dlg+0x250`, `SetState(0x14, 0)` | decompile | S |
| `0x14027ff30` | `LoadGameStep` ctor(this, bool continue) → `+0x88` | disasm | S |
| `0x140280280` | LoadGameStep update: continue → slot = `opts+0x49`; else waits for state[0x10b]==1 and slot = state[0x107]; checks slot used; `0x1402c9c50(slot)`; `0x1407552e0(1,0,0)` (start load) | decompile | S |
| `[GameDataMan]+0x58` (`0x140755d40`) | Options/profile data. `+0x49` = last-played slot (u8, 0xff none). `+0x10/+0x11` HUD-related bytes, `+0x12` (menu alpha/brightness?), `+0x15` lock-on option | decompile | S (field names G) |
| `[GameDataMan]+0x60` (`0x140755d80`) | Saved-characters preview data. `+0x10 + slot` (u8) = 1 if slot used (10 slots) | `0x140766840`, Overhaul `get_saved_chars_preview_data` | S C |
| `[0x141c74e08]+0xaa0` | GameMan current save slot (setter `0x1402c9c50`) | SoulSplitter `GetCurrentSaveSlot` + disasm | S C |
| `0x1402c9f70` | Save game to current slot (`GameMan+0xaa0`, 0x60000-byte buffer) | decompile | S |
| `0x1406a3c60(b)` | Load list: `SetState(0x1d, 5)` (load chosen) | decompile | S |
| `0x1406a3c90(b)` | `SetState(0x1d, 6)`, `SetState(0x10b, 1)` | decompile | S |
| `0x1406a38f0(slot)` | slot is used? | decompile | S |
| `0x1406a6650` | ProfileSelectList input: 0x85 decide → load; 0x9b → delete | decompile | S |
| `.sl2` I/O | Opened with `KERNEL32!CreateFileW` (import present). SaveLoad2 `SL*Session` classes + `FrpgSaveLoadMan` (vtable `0x1412db9b8`) | imports + RTTI | S |
| Slot size | DSR `.sl2`: slot data 0x60020 bytes (0x60190 variant), IGT at slot base + 0x2dc | SoulSplitter `Sl2Reader` | C |

**Load slot N (no UI):** at the title, write `opts+0x49 = N` (if `preview+0x10+N == 1`), then do what the title does for "Continue": `g_TitleResult = 0xb; SetState(0x14, 0)`. (RT)
**Load slot N from the Load Game list:** set the list cursor so `top+row == N` (or let a tap pick it), then decide (tap/confirm) → state[0x1d]=5 → LoadGameStep loads state[0x107]. (RT)
**Load any .sl2 file:** Overhaul method (source in `re/Dark-Souls-1-Overhaul/OverhaulDLL/src/Files.cpp`): hook `CreateFileW`, redirect any path ending `.sl2` to the chosen file. While the list is open (state[0x1d] is 3 or 4 and no character loaded): set state[0x1d]=0, copy the new file's preview data into `[GameDataMan+0x60]+0x10...`, set state[0x1d]=3 to rebuild the list. The later slot load reads the redirected file.

## 3. Lock-on

| Address | Meaning | How found | Conf |
|---|---|---|---|
| `0x141c7a138` | `LockTgtManImp*` (vtable `0x14133faa8`, size 0x1580, ctor `0x14040ad70`) | Overhaul + RTTI | S C |
| `+0x10 / +0x18` | head / tail of active candidate list (entries linked by `+0x30`) | `0x14040b0f0` | S |
| `+0x20` | free list; entries pool at `+0x30` (64 × 0x50) | ctor | S |
| `+0x1430` u8 | locked (bTargetLocked) | Overhaul + `0x14040d200` | S C |
| `+0x1431` u8 | lock request. InGameStep toggles it on the lock button: `+0x1431 = !+0x1430` | `0x14024f6b0` | S C |
| `+0x1432` u8 | force-unlock request | `0x14040b0f0` | S |
| `+0x1440` float | target-switch cooldown (0.5 after a switch) | `0x14040c2c0` | S |
| `+0x152c` float | lock range (lerped from param) | `0x14040b0f0` | S |
| `+0x1558` | player lock-param id | InGameStep | S |
| `0x14040b0f0` | `LockTgtMan::Update` (from WorldChrMan update). Builds candidates from global lock points `[0x141c7a130]+0x10` (linked by `+0x18`), scores them, gives the current target (flag 0x20) a sticky top score, sets 0x20 on the best one, then `0x1403222a0(player, 1, targetChr)` and copies target pos to `player+0x1b0` | decompile | S |
| `0x14040d200` | `GetCurrentTargetEntry()` (null if not locked) | disasm | S |
| `0x14040c2c0` | stick-flick target switch: moves flag 0x20 from old to new entry | decompile | S |
| `0x14040a480(lockpoint)` | lock point → owner `ChrIns*` (handle at lockpoint+0x14, class 0x1xxxxxxx) | disasm | S |
| `0x1403714b0(WorldChrMan, handle)` | ChrIns by handle (blocks at `WorldChrMan+0x440`) | disasm | S |
| `0x140371ed0(WorldChrMan)` | player ChrIns (`[0x141c77e88]+0xf0` override, else `WorldChrMan+0x68`) | disasm | S |
| ChrManipulator `+0x220` | `LockonTargetHandle` (player PadManipulator = ChrIns+0x70) | Overhaul `PadManipulatorStruct.h` | C |

Candidate entry (0x50 bytes, S): `+0x00` vec4 world pos of lock point, `+0x10` f32 distance to player, `+0x18` distance to camera, `+0x20` LOS timer, `+0x24` LOS grace timer, `+0x28` score, `+0x30` next, `+0x38` lock point ptr, `+0x40` flags (0x08 seen, 0x10 lockable now, **0x20 current target**, 0x40 LOS blocked, 0x80 LOS tick, 0x01 heap, 0x02 free). Full layout + tap-to-lock plan: `docs/LOCKON.md`.

**Tap-to-lock:** walk the entries (`+0x10` list), project `+0x00` with the camera (section 4), pick the one nearest the tap. Clear 0x20 on all, set 0x20 on the pick, set `+0x1431 = 1` (and `+0x1430 = 1` if not locked). The update keeps the 0x20 entry as best (sticky score), the same mechanism the stick-flick switch uses. (RT)

## 4. Camera and screen positions

| Address | Meaning | How found | Conf |
|---|---|---|---|
| `0x141c6e188` | `CameraMan*` (vtable `0x1412edf98`): `+8 + 8*i` = camera i. `GetCamera(i) = 0x140231370`; InGameStep uses `GetCamera(1)` = `[[0x141c6e188]+0x10]` | disasm + DSR-Gadget `CamManOffset 0x10` | S C |
| camera `+0x10..+0x4f` | camera world matrix (4 rows × vec4; row 3 = position) | `0x1400b6d90` (copy), view = inverse | S |
| camera `+0x50/+0x54/+0x58/+0x5c` | fovY (rad), aspect, near, far → D3D LH perspective (`0x14007c1c0`, uses fov*0.5) | disasm | S |
| `0x1406705c0` | lock reticle projection: `ndc = (p·View·Proj)/w`; reject if view z ≤ near; `x = (ndc.x*0.5+0.5)*W`, `y = (-ndc.y*0.5+0.5)*H`; W,H = `[[0x141b68ec8]+0x6f0]` float2 (render size) | decompile + consts `0x1412e6000`, `0x1412e5ff0` | S |
| `MenuMan+0xa20` | result of the above for the locked target (screen px + visible flag) | disasm | S |
| Menu design space | 1280 × 720 (`0x1412e1570`, `0x1412f6384`); dialogs scale by min(W/1280, H/720) | TargettingSite `0x14067e9a0` | S |
| Projection camera in InGameStep | `[[InGameStep+0x58]+0x18]` (may equal GetCamera(1)) | caller of `0x1406705c0` | S (equality RT) |
| ChrIns position | `ChrIns+0x68` (ChrCtrl) `+0x28` → `+0x10` vec3 (SoulSplitter `_playerPos`, PlayerCtrl offset 0x68) | SoulSplitter | C |

## 5. HUD

| What | Address | Conf |
|---|---|---|
| PC gauges (HP/stamina) visible if `state[0x78] ≥ 1` and `state[0x74] == 0` and not (`state[0] < 1` and `opts+0x11 ≠ 0`) | `0x14067bb20` | S |
| Setter used by the camera code each frame | `0x14071b7f0(show=cl, hide=dl)` (no effect if `state[0xad] ≠ 0`), shortcut HUD `0x14071b830(cl)` → `state[0x79] = !cl` | S |
| Whole HUD / menus suppressed | `state[0xad]` (MenuMan+0x2e4); rewritten every frame by InGameStep (`0x14071b430`) | S |
| HUD option bytes | `opts+0x10`, `opts+0x11` (opts = `[GameDataMan]+0x58`); names G | S/G |
| Overhaul visibility bit for menu objects | dialog `+0x18` list of objects, object `+0x28` bit 1 = visible | C |

Because the game rewrites these slots every frame, a persistent hide needs either the option byte (if `+0x11` is "HUD off") or a per-frame write after `InGameStep` (hook). (RT)

## 6. Runtime checks (agent DLL: read/write memory, vtable hooks, logs)
Do these in order. Each one names what to log.
1. **Menu state table.** Log `MenuMan+0x30..+0x7f0` diffs (500 ints) every frame while you open/close: menu bar, each tab, a yes/no box, title, Load Game. Confirm state[8] values (0/7/8/2), state[0x4b] tabs, state[0x1d]/[0x59]/[0x107]/[0x10b]. Also log `GetOpenMenusMask` (call `0x14071ac10` from a game-thread hook, or rebuild it from state reads).
2. **Mouse path.** Log MouseMan `+0x10..+0x40` and `PadMan+0x68` each frame. Then: force `PadMan+0x68 = 1`, return a fixed point from hooked `GetCursorPos`/`ScreenToClient`, and set DI mouse `rgbButtons[0] = 0x80` for 2 frames via the agent's GetDeviceState cache. Expected: menu bar tab under the point gets hover, then opens on click. If buttons do not reach `+0x10..0x12`, log which of DI / `GetAsyncKeyState(VK_LBUTTON)` feeds snapshot `[[0x141b68ec8]+0x700+8*idx]+8`.
3. **Open/close by state writes.** At gameplay: `state[0x7d]=1; state[8]=7` → menu bar opens? With bar open: `state[0x4b]=t` then open writes (`state[2]=1` / `state[3]=10` / `state[0x15]=1` / `state[0x2a]=1`, each with `state[8]=2`). Close-all: `state[0x88]=1`. Quit to title: `state[0x87]=2`. Watch for soft-locks.
4. **Load slot N.** At the title: `opts(+0x58)+0x49 = N`, `g_TitleResult(0x141a32240)=0xb`, `state[0x14]=0` → Continue loads slot N? Then the Load Game list: write ProfileSelectList `+0x21c/+0x214` (capture `this` by patching vtable `0x1413b9810` slot 16) and confirm. Then the `.sl2` redirect (CreateFileW hook) + `state[0x1d]=3` reload.
5. **Lock-on + projection.** Log LockTgtMan `+0x1430/+0x1431`, the entry list (pos, flags, owner handle) and `MenuMan+0xa20`. Project each entry with `[[0x141c6e188]+0x10]` and compare with `MenuMan+0xa20` for the current target (validates the camera and formula). Then the tap-to-lock flag write (move 0x20, set `+0x1431=1`); check `ChrManipulator+0x220` follows.

Lower priority: HUD option bytes `opts+0x10/+0x11` (toggle each, watch the HUD); listbox field layout on the inventory list (`FrpgMenuDlgInventory` and its list children); `IsAction` code map (log `0x140ed6750(this, code)` results while pressing each key).

## 7. Touch-size menus (2026-10-15, `tools/patch_menu.py` + `mod/dinput8/title.c` / `hud.c`)
All edits are in `menu.drb.dcx`; output `tools/out/menu.drb.dcx`, pushed by `tools/batch_test.sh`.
- **Scaling a dialog:** a Dialog shape's dest rect scales its child dialog (`DIALOG_SCALES`). Text glyphs do not scale with it.
- **Fonts:** Text byte +0x1c is a preset index into the .rdata table 0x1413d3950 (details: `FONTS_RE.md`). The agent sets presets 1 / 2 to 2.0x / 1.4x (`patch_fonts`). `FONT_BUMPS` points the menu lists at them. The game does not shrink text to its box, so boxes are widened.
- **System list (I06):** dialog x1.15 / y1.9, 2.0x font, rows widened to x 800. Divider lines and parchment sprites stretched with it (`STRETCH_DOWN`).
- **Item command menu (I01-01):** x1.5 / y2.0, 2.0x font.
- **Options (R01):** 14 rows → two columns of 7 rows, 68 units each (`option_rect`). Category labels and divider lines hidden. Parchment x1.5.
- **PC settings (R14-00 + R14-01):** 8 rows → one column, 58 units each, 1.4x font, label cell x 130..562 (`pc_rect`). Category labels and divider lines hidden. OK / Defaults +44.
- **Key settings (R13 / R15):** x1.1 and 1.4x font only (the list fills the height).
- **Inventory type strip:** the < > arrows are invisible (sprite colour 0).
- **Rule:** never scale the headers (`*_category_name`): they hold the tab click targets. A counter-scaled header came out misplaced.

### HUD in menus (`hud.c` `menu_hud`)
- The HUD option byte `[[0x141c8a530]+0x58]+0x11` is 0 while the menu bar / tabs, Display or Sound pages are open.
- Everywhere else it is locked to 1, including the System decide step (state[0x2a] == 3) and the Options / PC settings pages (they show a HUD row and read it at open).
- Locked ON since 2026-10-15 20:05: the old "restore the player's value" scheme kept a HUD OFF that got into the save (`PORTING_LOG.md`). A HUD OFF chosen on Options is undone when the menu closes.
- Own 2 ms thread: the decide step lasts a frame or two.

### System list without Key settings
- Entry 2 (Key settings) text and hit rect go off-screen; entries 3..5 move up one row (`SYS_ROW_Y`). The game still draws entry i in button<i>_0.
- Frame and parchment lose one row (`sys_trim`): the game's own 6 / 5 / 4 row variants differ exactly by 30 units per row.
- Rows scale y 2.1 (was 1.9): 63 units per row.

### Item command menu and message box (2026-10-15 20:20)
- **I01-01** (Use Item / Drop / Change Order / Reset Order): rows 65 child units apart inside the box (238..508), on top of the dialog's x1.5 / y2.0. The divider sprite `R03_note_line` (lines 30 apart) is hidden.
- **R09-00** = the general message box (FrpgMenuDlgGeneral, MenuMan state 0x11): up to 9 message lines, up to 3 buttons. Used by "Quit game?" OK / Cancel and "Game will start in offline mode." OK. Buttons 80 units high (`cursor_button0_*` hit rects 500..580), text at preset 2, box bottom 573 -> 593.
- `RECTS` in `patch_menu.py`: rect-only edits that keep origin and scaling type (plus an optional font).
- Other dialogs with OK / Cancel rows, not changed: F05-00 (cursor_button Mask), F14_00, `yesno` (in T04, the message-writing screen).
