# Bonfire menu list (Leave / Level Up / Covenant / Kindle / ...) — RE notes

DSR PC v1.04, base 0x140000000. Static analysis only (capstone + Ghidra headless, `re/ui/ghidra/dec.sh`). Nothing ran in the game. Scratch decompiles: `%TEMP%\claude\...\scratchpad\talk*.c` (session 2026-10-16).
Confidence tags as in `UI_RE.md`: **S** = seen in disassembly/decompile, **D** = seen in game data (DRB / ESD), **G** = guess, **RT** = needs a phone test.

## 0. Answer first

1. The bonfire list is **`FrpgMenuDlgTalkMsgbox` (vtable `0x1413ad058`) bound to DRB dialog `F04-01`**, created by the menu ESD `f04-00.esd` (in `menu/ingame.menuesdbnd.dcx`) as a *nested child* of the placement dialog `F04`. `F09` / `F09-06` is the bonfire **warp** list (`FrpgMenuDlgWarp`), reused by the DSR Covenant menu; it is not the Leave/Level Up list. (S, D)
2. The list is **not** sized by code. Its runtime rect is pushed every frame from the laid-out rect of the `F04-01` Dialog shape inside `F04` (`EzMenuDialog::Draw` → `0x140ed3b70` → `CMenuNestedDialog` slot 2 `0x140f01310` → child `+0xc4`). The child then lays out its rows with `scale = dest rect / own rect` — the same mechanism that makes the `I06` → `I06-00` scaling work. The DSR-added override in `TalkMsgbox::SetProperty` (`+0xc4 = {0,0,W,H}` px) is overwritten by that push before the dialog draws, so it does not change the geometry. (S)
3. Therefore the code says the existing DRB edit (`DIALOG_SCALES[('F04','F04-01')]` + `FONT_BUMPS['F04-01']`) **must** change the list. No code path overrides the Text font byte of `F04-01` either. The null phone result is inconsistent with the exe; the likely cause is that the tested file was not live (both an independent geometry edit and an independent font edit failed together). Re-test with a marker (section 4). (S + RT)
4. If a runtime method is still wanted (e.g. to keep the DRB stock, or if the re-test fails), scale the pushed rect from the agent DLL in the `TalkMsgbox` **Update (slot 16) and Draw (slot 19)** hooks: `dlg+0xc4..+0xd0` float rect, in render px, scaled about the frame's pivot. Section 5B has the exact recipe. Text size still comes from the DRB font byte (preset 2 = 1.4x, already patched). (S, RT)

## 1. Which class / which DRB dialog (evidence)

| Fact | Evidence |
|---|---|
| MenuMan state id 0x9 is owned by `FrpgMenuDlgTalkMsgbox` (7 sites), `FrpgMenuDlgTalk` (3), `FrpgMenuDlgNetworkOption` (1); ESD-side writer `0x14035a300` | `re/ui/menu_ids.txt` line 7 |
| `FrpgMenuDlgTalkMsgbox` vt `0x1413ad058`: ctor `0x14066a8f0`, dtor `0x14066a990`, Update `0x14066af30` (slot 16), SetProperty `0x14066aa50` (slot 27), OnEvent `0x14066abd0` (slot 35), input `0x14066b2f0` (36), cursor hooks `0x14066b540` / `0x14066b4e0` (37/38). Derives from `FrpgMenuDlgListbox` (vt `0x1413aad28`; slots 29/39 shared) | `re/ui/ctors.py` |
| It plays DRB scripts `F04_open_menu` (`0x1413ad240`) / `F04_close_menu` (`0x1413ad260`) on the placement dialog named `DIALOG_配置ダイアログ` (`0x1413a12d0`) | `0x14066af30` |
| It finds row texts by name `button%d_0` (`0x1412c8d78`), grey rows `grayout_drop%d`, `scrollbar`, highlight `cursor` | `0x14066ad10` (init), `0x14066b0c0` (refresh) |
| `FrpgMenuDlgTalk` vt `0x1413acc18` (Update `0x140669e40`) = the subtitle box `F04-00` (`DIALOG_会話テキストダイアログ`, scripts `F04_open_BG` / `F04_close_BG`) | `0x140669e40` |
| ESD `f04-00.esd` strings, in order: `menu:/menu.drb`, `DIALOG_配置ダイアログ` ← `F04`, `DIALOG_会話テキストダイアログ` ← `F04-00` ← `FrpgMenuDlgTalk`, `DIALOG_会話リストダイアログ` ← `F04-01` ← `FrpgMenuDlgTalkMsgbox` (twice: two ESD states) | `ingame.menuesdbnd.dcx` offsets 0x1109..0x1417 |
| The 5-string ESD command is `0x140ef53b0` → `0x140ee04d0(scene, placement, nestedObjName, ?, instName, className)`: creates the class instance, inits it from the DLG of the old child (`0x140ed4c20`), and **replaces the nested object's child** (`CMenuNestedDialog` slot 28 `0x140f01230`, copies the old child's rect `+0xc4` and parent `+0x60`) | decompile |
| `f09-00.esd`: `DIALOG_F09配置ダイアログ` ← `F09`, `DIALOG_ワープ選択ダイアログ` ← `F09-06` ← `FrpgMenuDlgWarp` (vt `0x1413c6c40`, SetProperty `0x1406ed340` plays `F09_open_menu`). `FrpgMenuDlgCovenant` (vt `0x1412c7750`, slot 27 `0x14013c790`) also plays `F09_open_menu` (DSR Covenant menu reuses F09) | ESD + string refs `0x1412c7910` |
| `FrpgMenuDlgTalkMsgbox` is the only class bound to `FrpgMenuDlgTalkMsgbox` in all three menuesdbnd files, and only to `F04-01` | string count: 4 `Talk` hits, all in `f04-00.esd` |
| `bk_PC_F04-01` in the DRB is an unreferenced backup copy ("PC版対応前" = before PC support); `bk_*` dialogs are dead data | DRB dialog list, no ESD/exe refs |
| The loose `menu/menu.drb` (806 KB, PTDE layout, 531 dialogs, no `F04_frame_PC`) is not what is drawn: the phone screenshot shows the DSR-only `F04_frame_PC` scroll arrows (`scroll_>` at 60..71 × 110..121 child units, on screen at (127,176) units = 67+60, 64+110) | `tools/out/bt_rest2.png` |

Screen geometry check (`bt_rest2.png`, 2640x1080, render 1584x648, 1 design unit = 1.5 screen px): row text left edge 212 px = 141 units (DRB `button0_0` left 138 + glyph bearing), row pitch 45 px = 30 units, first row glyphs at y 294..322 px inside the DRB box 191..219 units. So the list is drawn at **stock geometry, uniform H/720 scale, no x stretch, origin at the screen's left edge**.

## 2. How the list gets its size at runtime (S)

Per frame, for the `F04` group (`FrpgMenuSys::Step 0x140716690` → scene update `0x140ee17b0`):
1. For each top-level dialog entry: ESD state machine step (this is where `SetProperty` calls land) → `dialog->Update` (slot 16). Nested children are updated from the parent's `CMenuNestedDialog` shape, slot 24 `0x140f01320`: `child->vt[23](scalingType)` (`0x14013be10`, DSR: `child+0xf4`), `child->vt[25](origin)` (`0x14013be00`, DSR: `child+0xec`), `child->Update`.
2. Render: every `FrpgMenu*` dialog draws through slot 19 `0x140ed56d0`: `if (+0x178 == 0) 0x140ed9600 else 0x140ed8f60`.
   - `0x140ed9600` (normal dialogs, incl. placement `F04` and `F04-01`): `sx,sy = (+0xe6 ? dest/own : 1)`; `offset = dest.lt − own.lt`; then **layout pass `0x140ed4eb0`** (skipped when `+0xe6 != 0`), then **`0x140ed3b70`: for every object `obj->vt[20](laidOutRect[i])`** — for a nested Dialog shape that is `0x140f01310` = `0x140ed7bf0(child, rect)` = **`child+0xc4 = rect`**. Then each object draws; a nested shape draws its child (`0x140f00e50` → child slot 19).
   - Layout pass `0x140ed4eb0`: scale `sx = W/1280, sy = H/720`; when `H/W <= 9/16` both = `H/720 × dlg+0xf8` (uniform; `+0xf8` is synced from the scene's global scale `[dlg+0x1d8]+0x14`, normally 1.0). **If the dialog has a parent (`+0x60 != 0`): `sx = (dest.r − dest.l)/(own.r − own.l)`, `sy = (dest.b − dest.t)/(own.b − own.t)`** (`dest = +0xc4..+0xd0`, `own = +0xd4..+0xe0` = the DLG header rect, `(0,0,1280,720)` for `F04-01`). Shapes with scaling origin (−1,−1) are placed at `DRB rect × (sx,sy)`; anchored shapes (origin ≠ −1) are scaled about the anchor corner. Types 0x6e / 0x78 are not scaled (full-screen stretch). Output: `dlg+0x130` = per-object laid-out rects (render px for top-level dialogs).
   - `0x140ed8f60` (`+0x178 != 0`, nested shape flag byte +0x12 = 1, e.g. every `cursor` highlight dialog): per-object edge-anchored mapping of the own rect into the dest rect (function table `0x141a8da20`, .data), i.e. "stretch into rect". Not used by `F04-01` (flag 0x100).

Consequence for `F04-01`: parent `F04` is top-level, wide screen → its `F04-01` nested shape (DRB rect (0,0,1280,720), origin (0,360), type 1) is laid out at `(0,0,1152,648)` render px and pushed into the TalkMsgbox's `+0xc4` every frame. The TalkMsgbox has a parent, so its rows scale by `dest/own = 1152/1280 = 648/720 = 0.9` — exactly what the screenshot shows. **Scaling the nested shape rect in the DRB scales the whole list (rows, frame, cursor rects, hit rects), like I06-00.** With `(1.4,1.6)` about `(67,355)` the pushed rect becomes about `(−24,−192,1589,845)` px → rows 30 → 48 units, text box widths ×1.4.

The DSR override: `TalkMsgbox::SetProperty 0x14066aa50` ends with `dlg = FindDialog(scene, "DIALOG_会話リストダイアログ")` (= itself) and `0x140ed7bf0(dlg, {0, 0, W, H})` with `W,H = [[0x141b68ec8]+0x6f0]` (render px). ~60 dialog classes do the same (`calls_to(0x140ed7bf0)`), normally on their **placement** (`DIALOG_配置ダイアログ`, e.g. System `0x1406f3d00`, ContentsHelp `0x140741a50`); Talk / TalkMsgbox apply it to themselves. It runs only when the ESD sets a property (open / init / close), and the parent's draw overwrites it the same frame, so it is harmless for drawing. It matters only for hit-testing in that one frame.

Text size: `CMenuTextShape` draws with the font preset from the DRB Text byte +0x1c (copied to shape+0x2c at creation, `FONTS_RE.md`). The talk rows are dynamic texts (DRB Text param +0x1f = 2, same as the R03 buttons and the title rows, where font edits work). `TalkMsgbox` only calls `SetText` (`0x140edbd90` → shape slot 25) and the grey-out flag (`0x140edbdb0`, obj+0x28 bit 1). No code writes the font. Dialog scaling (section 2) does not scale glyphs (laid-out boxes grow, glyph size does not), as seen on I06.

## 3. Why the phone test showed nothing (ranked)

1. **The tested `menu.drb.dcx` was not live for that run** (G, most likely). Two independent edits (nested rect, Text font byte) that both work on other dialogs through the same code paths both failed. Check with a marker edit (section 4).
2. The edit was applied to the wrong copy: `tools/out/menu.drb.dcx` now contains the F04 and F04-01 edits (verified: `F04/F04-01 → (−27,−213,1765,939)`, `button*_0 font 2`), but the output file is dated 18:11, after the 17:48..18:10 bonfire screenshots. The screenshots may predate the rebuild.
3. Not the cause: the DSR `+0xc4` override (overwritten each frame, section 2), `F09`/`F09-06` (warp list), `bk_PC_F04-01` (dead data), the loose PTDE `menu.drb` (not drawn), a code-set font (none).

## 4. Cheap validation test (RT)

Push a file with an unmistakable marker in `F04-01` besides the scaling, e.g. `FONT_BUMPS['F04-01'] = {8: 1}` (2.0x) for one round, or move `F04-01/scrollbar` to x 300. If the marker shows, the DRB path works and the (1.4,1.6) scale will show with it; tune from there. If the marker does not show while other menus do, the F04 group is being loaded from somewhere else and section 5B (runtime hook) is the fallback that does not depend on the DRB.

## 5. Data-only ways to make the rows taller and the text bigger

### 5A. DRB (already in `tools/patch_menu.py`; keep it)
- `DIALOG_SCALES[('F04','F04-01')] = ((1.4, 1.6), (67, 355))`: scales the pushed dest rect → rows 30 → 48 units, hit rects (`cursor<i>_0`, used by the Listbox for the highlight and registered as controls 100+i) scale with it, frame `F04_frame_PC` and `BG` scale with it.
- `FONT_BUMPS['F04-01'] = {8: 2}`: 1.4x glyphs (agent `patch_fonts` sets preset 2 = 1.4x). Row box 28 → 45 units high after scaling, 1.4x glyphs are 34 units: fits. Preset 1 (2.0x = 48 units) would not.
- Only 11 rows exist (`button0_0..button10_0`); the bonfire list has 5..8 entries, so no scrolling issue. Rows 191..519 units → 93..618 after the y1.6 about 355: inside 720.
- Do not scale `F04` itself or `F04-00` (subtitle box). `F09` edits can be removed (warp list).

### 5B. Runtime hook from the agent DLL (no DRB geometry change needed; `.rdata` vtable write only)
Pattern = `title.c: hook_title` (vtable slot swap). Target vtable `0x1413ad058` (`FrpgMenuDlgTalkMsgbox`, its own copy, so other classes are untouched):
- slot 16 `+0x80` → `0x1413ad0d8` = Update `0x14066af30(dlg, float dt)`
- slot 19 `+0x98` → `0x1413ad0f0` = Draw wrapper `0x140ed56d0(dlg, dc)` (shared base code, but the slot is per class)

Hook body (both slots, after calling the original for Update, before calling the original for Draw):
```c
/* dlg+0xc4..+0xd0: dest rect {l,t,r,b} float, render px, pushed by the parent F04 every frame.
   own rect dlg+0xd4..+0xe0 = (0,0,1280,720). Rows scale by dest/own, so scale dest about the
   frame pivot (67,355) design units like the DRB edit. s = px per design unit = (b-t)/720. */
float *r = (float *)(dlg + 0xc4);
float s = (r[3] - r[1]) / 720.0f;
float px = r[0] + 67.0f * s, py = r[1] + 355.0f * s;
r[0] = px + (r[0] - px) * KX;  r[2] = px + (r[2] - px) * KX;
r[1] = py + (r[1] - py) * KY;  r[3] = py + (r[3] - py) * KY;
```
Guard: only when `(r[2]-r[0]) / (r[3]-r[1])` is still 1280/720 (i.e. the stock pushed rect), so the scale is not applied twice; skip when the rect is the DSR `{0,0,W,H}` override (aspect = W/H). KX=1.4, KY=1.6 reproduce 5A. The Update hook keeps the hit-test transform (`EzMenuDialog` slot 10 `0x140ed4220` → `0x140ed9ef0`, uses dest/own) consistent with the draw; the Draw hook applies it after the parent's push. This is the same thing the game does for floating HP bars (`FrpgMenuDlgFloatingPCGauge 0x1406f61a0`: parent nested object `0x140ed6800(dlg)` → `obj->vt[20](&rect)` and `0x140ed7c00(parent, objIdx, &rect)`); writing the parent's laid-out entry (`parent+0x130 + 16*idx`) instead of the child would also survive the push, but needs the object index.
Text: unchanged by the hook; keep `FONT_BUMPS['F04-01']`.
Confidence: mechanism S; exact pivot/px units RT (one phone round).

### 5C. Not recommended
- `dlg+0xe6 = 1` ("stretch into rect", used by FloatingPCGauge / ContentsHelp cursor): skips the layout pass and scales through the DC transform; might also scale glyphs, but changes hit-testing semantics and the cursor child. Only as an experiment.
- Scene global scale `[dlg+0x1d8]+0x14` (`+0xf8` per dialog): scales every dialog of the in-game scene (HUD included).
- `+0x178 = 1` (edge-anchored mapping path) or the nested shape flag byte +0x12: changes the draw path of the whole list; untested semantics.
- The DRB scripts (`F04_open_menu` / `F04_close_menu`, 23 keys each; key names include `cursor<i>_0` and `scrollbar`) are open/close fades played on the placement. The row rects come from the `F04-01` shapes, not from the scripts (SCDK/SCDO/ANIK layouts not fully decoded).

## 6. Reference: offsets and ids (S)

`EzMenuDialog` (base of every `FrpgMenuDlg*`):
| Off | Meaning |
|---|---|
| +0x18 / +0x20 | object array / count (`EzMenuDlgObj*`: +0x18 owner dialog, +0x20 shape, +0x28 flags (bit1 visible, bit2 grey), +0x30 DLGO entry) |
| +0x58 | pre-draw hook object |
| +0x60 | parent dialog (0 = top-level) |
| +0xc4..+0xd0 | dest rect l,t,r,b (float). Top-level: own rect; nested child: pushed by the parent each draw |
| +0xd4..+0xe0 | own rect from the DLG header shorts +0x28..+0x2e |
| +0xe4 / +0xe5 / +0xe6 | visible / alpha / stretch flag |
| +0xec, +0xf0, +0xf4 | DSR anchoring: origin x,y (float), scaling type (int), set from the parent's nested shape each update |
| +0xf8 | scale multiplier (synced from scene +0x14) |
| +0x108 / +0x110 | per-object DRB rects (float4) / count; +0x130 per-object laid-out rects (float4) |
| +0x178 | draw path: 0 = `0x140ed9600` (layout), 1 = `0x140ed8f60` (edge mapping) |
| +0x1d8 | scene (+0x14 global scale) |
| +0x1f8 | 8 animation tracks × 0x20 |

`FrpgMenuDlgListbox` / `TalkMsgbox` fields: +0x208 visible rows (prop 3000), +0x20c columns (0xbb9), +0x214 cursor row (0xb54), +0x218 total rows (0xbbb), +0x21c top (0xb55), +0x224/+0x225 dirty flags, +0x230 scrollbar object, +0x240 "input owner" (if `[+0x240]+0x60 != 0` input is ignored), +0x250 chosen index (−1), +0x25c last open flag, +0x260 open request (prop 0x3f8: 1 open, 2 close → `F04_open_menu` / `F04_close_menu`), +0x264 / +0x268 state[9] current / previous. Props: 0x3ec = (re)build list, 0x3ed = decided (`0x14071ba80(+0x250)`), 0x3f8 = open/close. Controls: rows registered as ids 100+i (`0x140719950`), scrollbar 99. Events: click (2) on id 100+i selects, hover (8) moves the highlight, right click (6) with id 99999999 cancels, wheel (0xc) scrolls.

MenuMan: `+0xba0` talk list data (getter `0x14071ba20`; `[+8]` = vector of 8-byte entries, `+0` = FMG text id via `0x14053cd40`), `+0x808` talk text state (getter `0x14071b870`; +4 = next-page icon flag), `+0x828` (getter `0x14071bcf0`; +0x10 set to 0.7 each update while the list is open).

ESD → EzMenu commands seen: 5-string create-in-nested-object `0x140ef53b0` → `0x140ee04d0`; rect copies `0x140edfbd0` (dialog ← dialog) and `0x140edfd40` (dialog ← object rect of another dialog) via `0x140ef1810` / `0x140ef1b30`.

DRB Dialog shape params (SHPR, 0x20 bytes): rect L,T,R,B (i16×4), origin X,Y (i16×2), scaling type (i32), **+0x10 u16 DLG index, +0x12 u16 flags (0x100 normal, 0x101 = stretch child, used by all `cursor` highlights)**, then 0, −1, 0. The "+0x20 source rect" in `patch_menu.py`'s docstring is the next shape's rect, not part of the Dialog shape. The DLG header (0x40 bytes): +0 name, +4 shape, +8 ctrl, +0x20 object count, +0x24 DLGO offset, +0x28..+0x2e own rect (i16×4).

## 7. Bonfire "fog" overlay (secondary item, from a parallel sweep; nothing confirmed)

Facts found: it is not a DRB object (every full-screen MonoRect/GouraudRect uses the stretch types 0x6e/0x78 and would cover the full width; `F23_Bonfire` is only the "BONFIRE LIT" banner; `F09` has no full-screen object). It is not the fade plate (`FrpgMenuDlgFadePlate` rect `0x1406e3b70` = full render size, colour from FadeMan `[0x141c86518]+0x160`). `CampStep` is a debug step. No menu texture looks like a fog/vignette; no 2.4-aspect constant exists in .data/.rdata. 98.3% of 1584 px / 648 px = aspect 2.40: the effect covers a 2.4:1 area, i.e. a fixed-size quad seen through the Hor+ camera, like the known Seath screen effect.
Best candidates (G):
1. SFX `f0090012` in `sfx/FRPG_SfxBnd_CommonEffects.ffxbnd.dcx`: the only FFX the player's sit-down animations fire (TAE `a00` anims 7700/7710/7720, FFX 90012 on dummy 236 at 0.67 s).
2. SFX `f0090016` / `f0090015` (anim 7725, dummies 229 / 1, with fade events 193); 90016 may use texture `s00912` (yellow ragged ring, vignette-like).
3. A renderer pass (`EzFilterDrawEntity` vt `0x1412ab088`, draw `0x1400ba7d0`), unlikely (full-screen).
Data-only fix once confirmed: scale the quad width of the FFX by about 1.06 and repack the bnd. Confirm with one phone round: replace the FFX by an empty FFX such as `f0090005` in a copy of the bnd; whichever removes the fog is the one to widen.

### 7.1 FFX analysis (`tools/fog_ffx.py`, PC only, not yet tested on the phone)
Tool: `python tools/fog_ffx.py analyse [ids]` decodes FXR1 (DSR wide layout, after SoulsFormatsNEXT `FXR1`). `build` writes the outputs below into `tools/out/` and verifies each one (same entry count/names/ids, only the intended bytes differ). `containers.py` now has `bnd3_write` / `bnd3_raw_entries`; an unchanged rebuild is byte-identical. `FRPG_SfxBnd_Patch` has no 90010/90012/90015/90016 entry, so CommonEffects is the only source.
- `f0090012` (S): **not the fog.** It is the sit-down flame flare: billboards 59/70/71, textures 1036 / 15392 / 20003, orange colours, 0.75 s, world-space sizes 0.05..5 m, not attached to the camera.
- `f0090015` (S): no appearance block. One action 87 with 16 zero parameters. Not the fog.
- `f0090016` (S): no appearance block. Action 14 (call child effect) → **`f0090010`**.
- `f0090010` (G, best candidate): action 70 (3-texture billboard) with texture `s61409` (512², tiling grey fog/heat noise), **Attached = 1, RenderDepth = −1500, blend 6**. It is the only 70/71 block of the 1,712 CommonEffects entries with a large negative RenderDepth. Colour orange-white, alpha 0→1→1→0 over 3 s, UV scroll. Plus action 43 (heat distortion), Unk1 −2500.
- Width values in `f0090010.ffx` (offsets inside the .ffx): action 70 @0x1320: `Scale1X` const 2.75 @0x1600, `Scale1Y` empty, **`Scale2X` const 1.375 @0x1604**, `Scale2Y` const 1.0 @0x1608. Action 43 @0x11b0: **`ScaleX` const 3.0 @0x12d8**, `ScaleY` 4.125 @0x12dc, `ScaleZ` 1.0 @0x12e0. Each float belongs to one field only.
- Widen choice: `Scale2X` (X only; an empty `Scale1Y` may follow `Scale1X`, so `Scale1X` could also grow the height). 70 `Scale2X` 1.375 → 1.4575, 43 `ScaleX` 3.0 → 3.18 (×1.06, in place).

Outputs (copy one at a time over `sfx/FRPG_SfxBnd_CommonEffects.ffxbnd.dcx` on the phone, keep the original):
| File | Content | Size |
|---|---|---|
| `tools/out/fog_test_empty_90010.ffxbnd.dcx` | `f0090010` → `f0090005` body, root id patched to 90010 | 67,444,442 B |
| `tools/out/fog_test_empty_90012.ffxbnd.dcx` | `f0090012` → `f0090005` body, root id patched to 90012 | 67,443,077 B |
| `tools/out/FRPG_SfxBnd_CommonEffects.ffxbnd.dcx` | `f0090010` widened ×1.06 (2 floats) | 67,445,433 B |

Test order: one round with `fog_test_empty_90010` (expect: no fog). If the fog stays, test `fog_test_empty_90012`, then widen that one: `python tools/fog_ffx.py build --widen-id 90012` (scales `Scale2X` of its 70/71 blocks and `ScaleX` of its 59 block). Original size: 67,445,412 B.

## 8. Open points (RT)
- Section 4 marker test decides between 5A (DRB, expected to work) and 5B (hook).
- 5B pivot / px math: one round to confirm the list lands where the DRB variant would (rows 93..618 units).
- Does the DC transform scale glyphs in `+0xe6` mode (5C)? Not needed if `FONT_BUMPS` is kept.
