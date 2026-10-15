# Touch controls (DSR mode)

Source of truth: `design/final_wanted_controls.html` (rev 31, Galaxy Z Flip6).

## How it works
- **Layout** = `opennative-src/app/src/main/assets/inputcontrols/profiles/controls-6.icp` (Winlator JSON). XServerScreen copies it to the profiles dir on each launch and loads it.
- **Behaviour + drawing** = `app/gamenative/dsr/DsrTouchControls.java`. It reads the elements from the profile, draws them (Bone & Ash skin) and owns every gameplay touch.
- **Glue** = DSR blocks in `com/winlator/widget/InputControlsView.java`:
  - Gameplay (`DsrGameState.isGameplay`): touches go to `DsrTouchControls`. The generic Winlator elements are not drawn.
  - Menu / title / loading: the existing menu layer (✓ = A, ✕ = B, swipe = d-pad, tap = mouse click).
  - Phase change out of gameplay: all inputs are released.
  - Edit mode: the generic Winlator editor still works on the same profile.
- **Back gesture** (`XServerScreen.gameBack` → `InputControlsView.dsrBack`): Start in gameplay, B in menus. On the title / loading screens, back still opens the app quick menu (exit etc.).

## Role of each element
The first binding of an element sets its role. Its position, size and label come from the `.icp`.

| Design element | `.icp` element | Behaviour in code |
|---|---|---|
| Floating stick (home over the left bar) | `STICK` | Spawns where the thumb lands in the float zone (left edge → stick + 256 dp, stick − 66 dp → bottom). Drag = L-stick. Release = back home. |
| Sprint | (stick) | Second stick touch ≤ 300 ms after the previous one = B held until that finger lifts. |
| Attack 104 dp | `BUTTON` R1 | 80 ms window. Rise ≥ 12 dp in the window = Strong mode, else R1 fires at 80 ms (or at lift if earlier). Strong: chevrons; ≥ 30 dp = armed; release armed = R2; back under 30 dp = cancel. The finger stays owned by Attack. |
| Block 76 dp | `BUTTON` L1 | L1 held. Parry = the strong-attack gesture: slide up ≥ 12 dp (thumb circle + chevrons), armed at 30 dp (ember pulse), release = L1 up + L2 pulse; released before armed = just L1 up. Slide onto Attack = R1 pulse with L1 held (guard attack). |
| Roll 76 dp | `BUTTON` B | Plain hold. Backstep and jump (while sprinting) come from the game. |
| 2H | `BUTTON` Y | Plain. Hit area 48 dp. |
| Menu bar | `BUTTON` START, `ROUND_RECT` | Plain. |
| Estus / quick item 88 dp | `BUTTON` D-pad down, `SQUARE` | Tap → waits 250 ms: no second tap = d-pad ↓ (next item); second tap = X (use). Horizontal drag: first step at 22 dp, then every 40 dp; → = next, ← = previous (stub). |
| L-hand · spell · R-hand row 56 dp | `BUTTON` D-pad ← ↑ →, `SQUARE` | Plain press on touch-down (no delay). |
| Interact pill | `BUTTON` A, `ROUND_RECT` | Plain. Always visible above the row (see stubs). |
| Camera | free area | Drag = R-stick (7 dp per move event = full tilt; back to 0 after 60 ms idle). |
| Lock-on | free area | Tap (< 180 ms, < 8 dp) = R3 pulse. While locked, a camera flick switches target (game behaviour). |
| Slide-through | plain buttons | A finger that slides onto another plain button releases the old one and presses the new one. |
| Hit areas | all buttons | Never below 48 dp. Overlaps: nearest centre wins. |
| Visibility | all | Shown only in gameplay. 45 % opacity, 70 % while any finger is down. 150 ms fade in / out. |

## Stubs and limits (TODO)
- **Tap-to-lock a specific enemy**: needs enemy screen positions and a way to set the target. The app can read but not write game memory → needs the agent DLL. Now: tap = R3 (game picks the target). `DsrTouchControls.lockOn`.
- **Previous quick item** (done 2026-10-15): the game has only "next", so previous = next × (filled quick slots − 1). Slots counted from PlayerGameData+0x438. Untested with more than one quick item.
- **Interact pill** (done 2026-10-15): shown only while MenuMan+0x828 > 0 (map-action prompt) or the item-get popup waits (+0x81c ≠ −1, label "OK"); replaces the L · spell · R row with a 250 ms cross-fade; label = the game's prompt text (`dsr_assets/prompts.json`, e.g. 10010103 "Pick up item"); the pill widens to fit. The agent hides the stock prompt box (`mod/dinput8/hud.c`).
- **Equipment icons** (done 2026-10-15): Attack = right weapon, Block = left weapon, row = left / spell / right, Estus = selected quick item + count. Ids from PlayerGameData (re/RE_NOTES.md), icons from `<game>/dsr_assets/` made by `tools/extract_assets.py` from the user's own game files. No assets → text labels. With assets, the agent hides the stock slot block. Leftover: the quick item's name line still draws.
- **Lock-on opacity (70 % while locked)**: needs the lock-on flag (LockTgtManImp+0x1430/0x1431, not wired). Now: 70 % only while touched.
- **Not in the APK scope**: HUD mod (bars / souls moved), edge glow (to be replaced by native-aspect rendering, docs/ui/ASPECT_RATIO.md), enlarged main-menu items → game / DLL / render work.
- **Menus** (updated 2026-10-15 20:05): swipe = d-pad steps, tap = click, ✓ / ✕ buttons (`InputControlsView.dsrMenuTouch`).
  - Hover: 110 ms after touch-down if the finger has not moved (`DSR_HOVER_DELAY_MS`). Not at touch-down: the game snaps the selection to the hovered row, so a swipe started on an item selected it first.
  - Click at lift, at least 60 ms after the hover (one late frame missed a 40 ms gap).
  - Swipe: one axis per swipe (fixed at swipe start), 90 px per step, d-pad taps 100 ms apart (70 ms press). A backlog over 3 steps is dropped, so the list stops when the finger stops. A flick (> 1500 px/s) adds 1..5 steps.
  - Title: only the one-row main menu uses the agent pick (`dsrTitleRow`). The title sub-screens (System list, Options, Load Game ...) use hover + click like the in-game menu (`dsrMouseScreen`).
- **Press length**: every press lasts ≥ 80 ms (the game polls once per 33 ms frame; instant taps were missed by Start and ✕).
- **Startup**: the agent removes the "Game will start in offline mode." notice in code (PORTING_LOG 2026-10-15). Fallback when the patch bytes differ: the app presses A every 700 ms while a general dialog is up on the bare title (max 8) (first general dialog per run, MenuMan +0x74) and clears the save's "not closed with Quit Game" flag before launch (`DsrLauncher.clearQuitFlag`).
- **Sizes scale with screen width** (Winlator `scale` × width/100), not with dp. They match the design on the Flip6 only.
- **Sprint**: B is pressed at the second touch. If the finger lifts quickly, the game sees a short B = roll.

## Tweak positions and sizes
Edit `controls-6.icp` (copied over the profile on each launch), then rebuild.
- `x`, `y` = centre as a fraction of the view (Flip6: `x = dp / 992`, `y = dp / 406`).
- `scale`: Flip6 snap = 26 px = 9.77 dp. Radius / half-size in dp:
  - `CIRCLE` button: 3 × 9.77 × scale.
  - `SQUARE`: 2.5 × 9.77 × scale.
  - `ROUND_RECT`: 4 × 9.77 × scale wide, 2 × 9.77 × scale high.
  - `STICK`: 6 × 9.77 × scale.
- `text` = label drawn on the control.
- To change a role, change the first binding (see the table).
- Timing and distance rules = constants at the top of `DsrTouchControls.java`.
- Skin colours = `FILL`, `RIM`, `INK`, etc. in the same file.
- The in-app controls editor also edits the profile, but the next launch overwrites it from the asset.

## Feedback visuals (2026-10-15)
- Strong attack (swipe up from Attack): a small circle follows the thumb with the >>> chevrons above it. Once armed (≥ 30 dp rise) both turn ember orange and an ember ring pulses out of Attack until release (R2).
- Only the control under a finger brightens (idle 0.45 → held 0.70 alpha).
- Attack, Block, Roll are 10% larger (controls-6.icp).
- Stock HUD moved by `tools/patch_menu.py` (menu.drb.dcx): HP / stamina + humanity ring right of the Estus slot, souls box under them (number left-aligned, gained souls to its right), status icons under the souls box, quick item name centred under the Estus slot.

## Camera, two-handing, title (2026-10-15 afternoon)
- Camera drag = finger speed -> right stick: velocity filter 28 ms, full stick at 520 dp/s, output starts past the game's stick dead zone (0.16), eases out over ~45 ms after the finger stops. The agent (cam.c) makes the follow camera turn 1.5x faster. Measured: 300 px drag in 600 ms = 22 deg (stock mapping: 2.6 deg). Tunables: DsrTouchControls CAMERA_*, cam.c CAM_SPEED.
- Strong attack: chevrons run from the Attack centre to the thumb circle, pointing at the thumb.
- Two-handing (2H button): Block and Attack show the two-handed weapon (L1 guards with it); the off-hand slot in the bottom row dims.
- Title: "TOUCH TO START" (any tap = A). Main menu: one row of 5 entries (Log In hidden offline); tap an entry = pick it; swipe left/right = step; ✓ = confirm.

## Layout anchors (2026-10-15 20:20)
- 2H: same centre height as Menu, diameter = Menu height (scale = Menu scale x 2/3), placed left of Menu with a gap of 1/6 of the Menu height (`ControlsProfile.anchorTwoHandToMenu`).
- Menu button, Interact pill, menu action buttons (Back / Status / Display): translucent fill + bronze rim, no parchment.
- Phase debounce (2026-10-15 21:10): leaving LOADING must hold 500 ms (`DsrGameState.settle`, `LEAVE_LOADING_MS`). During loading screens the game briefly shows a player / ticking IGT / menu state, and the app flashed the controls and Back. Hidden blips are logged as `phase blip during LOADING`.
- 2026-10-15 21:28: backstep icon = figure hopping back (stride, guard arm forward, speed lines, ground line); roll icon unchanged. Bottom slots: centres 0.423 / 0.5 / 0.577, scale 1.22. Interact pill: bronze outline grows 7 dp and fades every 1.8 s (`drawInteractPulse`, redraw ~30 FPS while the pill is up).
