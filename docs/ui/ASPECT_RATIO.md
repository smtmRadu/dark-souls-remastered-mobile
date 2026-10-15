# Native phone aspect ratio (Hor+) for DSR on Android

Static analysis of exe 1.03.1 (base 0x140000000) plus community sources. Nothing here ran on a phone yet.
Confidence tags as in `UI_RE.md`: **S** = seen in disassembly/decompile, **C** = community source, **RT** = needs a runtime check.

## 1. Findings (read this first)

1. **DSR is already Hor+ with an aspect-aware HUD. No aspect patch is needed.** There is no PC ultrawide fix for DSR, because none is required. PCGamingWiki: ultrawide "Hor+", the only bug is UI above 3840 px width. Steam users at 2560x1080: gameplay, HUD and real-time cutscenes are 21:9; the pre-rendered intro is 16:9. (C)
2. The exe confirms it (S):
   - Camera aspect = render W / render H, fovY fixed at 0.7505 rad (43 deg). Horizontal FOV grows with width: 70 deg at 16:9, 80 deg at 2.144 (S23 Ultra), 88 deg at 2.444 (Flip6).
   - Every UI scale site uses `scale = (H/W <= 9/16) ? H/720 : W/1280` and the menu layout anchors each element to its nearest screen corner. Wider screens keep a 720-high design space and get more horizontal room. Menus are not stretched.
   - Bink movies get native side bars (a dedicated pass draws black quads when aspect is not 16:9).
3. **Today's black bars come from the app, not the game.** The Wine virtual desktop and X screen are 1280x720 (`Container.DEFAULT_SCREEN_SIZE`). The game picks the largest display mode, which is 1280x720. The Winlator renderer then fits 16:9 into the 22:9 view (`ViewTransformation`), which adds the side bars.
4. **The real work is the render resolution.** Set the X screen / Wine desktop to a phone-aspect size, for example 1584x648 on the Flip6 and 1544x720 on the S23 Ultra. The game then uses that size at boot. The DLL makes sure the saved PC option (screen mode and size) cannot pull it back to a 16:9 mode.
5. Hard limits in the exe: display modes below **800x600 are dropped** (patchable), and UI breaks above **3840 px width** (C). 1584x648 and 1544x720 both pass.

**Feasible: yes. Effort: about 0.5 day for the app and DLL, plus about 0.5 day of phone testing.** No `.text` patches are needed for the main path.

## 2. Exe sites (v1.03.1)

### 2.1 Resolution and mode list (the part that matters)
| Address | Original bytes | What it does | Action | Conf |
|---|---|---|---|---|
| `0x1401b7a50` | – | App init: enumerates DXGI display modes into the list `[0x141c6af10..0x141c6af18)` (0x1c-byte entries: w, h, refresh n/d, format, ...). Keeps modes <= `GetSystemMetrics(SM_CX/CYSCREEN)` in `[0x141c6af30..0x141c6af38)`, sorts and dedupes them, and adds the desktop size at `0x141c6af48/50`. Init struct `[0x141c6aee8]`: **+0x34/+0x38 = W/H of the last (largest) mode**. | none | S |
| `0x1401b7d21` | `81 3B 20 03 00 00` | `cmp [rbx], 800`: drops modes with width < 800 | Only to allow an internal height < 600: imm32 -> `0x00000001` | S |
| `0x1401b7d29` | `81 7F E8 58 02 00 00` | `cmp [rdi-0x18], 600`: drops modes with height < 600 | as above | S |
| `0x1401b8340` | – | Window creation: `CreateWindowExW` with client size = init +0x34/+0x38. Then it loads `DarkSouls.ini` (`0x1401b6620`, sections DisplaySetting/DisplaySettingWindow/DisplaySettingFullScreen; default Width/Height = init +0x34/+0x38, else 1280x720) | none | S |
| `0x14015e230` -> `0x14015f820` | – | Graphics init: **render size float2 = init +0x34/+0x38**, stored at `[[0x141b68ec8]+0x6f0]`. Nothing writes it again later (no other store found). All render targets are created at this size. | none | S |
| `0x1402055c0` | – | Applies the PC display option. Options = `[[0x141c8a530]+0x68]` (GameDataMan): **+0xc4 screen mode (0 fullscreen, 1 window, 2 borderless = desktop size)**, +0xd0/+0xd4 window W/H, +0xd8/+0xdc fullscreen W/H, +0xe4 format, +0xe8 refresh. Checks the size against the mode lists. If not found, falls back to init +0x34.. (and mode 1). Sends render command `0x8097`. Called from `0x14025e020` / `0x14025e0e0`. | DLL writes these fields (section 3) | S, trigger RT |

Wine side (Proton 9 = Wine 9, `win32u/sysparams.c`, virtual desktop): the mode list = the standard table (4:3, 5:4, 16:9, 16:10 sizes) filtered to <= the X screen, plus the desktop size itself.
- X screen 1584x648: the game's list = {800x600, 1584x648}, so init picks 1584x648.
- X screen 1544x720: the list = {800x600, 1280x720, 1544x720}. A saved 1280x720 option stays valid, so the DLL must override it.

### 2.2 Camera / FOV (no patch)
| Address | Bytes | Meaning | Conf |
|---|---|---|---|
| `0x140247190` | `C7 43 50 37 20 40 3F` @ `0x1402471c4` | Camera ctor: fovY = 0.7505 rad, **aspect (+0x54) = W/H** from the render size (`divss` @ `0x1402471d9`), near 0.05, far 3100 | S |
| `0x140247280` | – | Camera SetFov: recomputes aspect = W/H on every FOV change | S |
| `0x14007c1c0` | – | D3D LH perspective from +0x50/+0x54 (fovY, aspect): Hor+ | S |
| `0x1411bdbb0` | uses `0x141615c74` = 1.7777778 | A utility camera with fixed fov 90 deg and aspect 16:9 (not the player camera; this is the only code use of 16/9). Leave it as is. | S (purpose RT) |

Optional FOV clamp: if 88 deg feels too wide on the Flip6, the DLL can scale camera +0x50 after the game sets it. A clean hook point is `0x140247280`. This is not needed for correctness.

### 2.3 HUD / menus (no patch, native anchoring)
Design space constants: 1280 at `0x1412e1570`, 720 at `0x1412f6384`, 9/16 at `0x1413ab470`. The "fit by height when wider than 16:9" test (`comiss H/W, 0.5625`) is at:
`0x140662fe3, 0x140673704, 0x14067ea4e, 0x1406f6266, 0x140725c21, 0x140ed50ff, 0x140ed6601, 0x140ed6647, 0x140ed9005, 0x140ed9730` (S).
- `0x140ed4eb0` = the menu layout pass. Each element is anchored to a corner quadrant (1..4) and scaled uniformly. Types 0x6e/0x78 stretch on purpose (full-screen backgrounds). (S)
- MouseMan/tap mapping uses the client rect -> render size, so it follows automatically (UI_RE 1.5).

Known cosmetic exceptions (RT, low priority):
| Address | What | Effect at 22:9 | Optional fix |
|---|---|---|---|
| `0x14025bcf0`, `0x14025c2a0` (`movss xmm2,[0x1412e1574]` @ `0x14025be2d` `F3 0F 10 15 3F 57 08 01`, @ `0x14025c410` `F3 0F 10 15 5C 51 08 01`) | Title screen (`title_prototype`, `title_press_start`) drawn in a fixed 1920x1080 2D space | Title logo and "Press start" stretched about 1.37x horizontally | Repoint the disp32 to a DLL float = 1080*W/H **and** offset x by (Vw-1920)/2 (needs `0x1401d82d0` rect semantics, RT). `.text` patch, so check anti-tamper first. |
| `0x14025ddb0` | Loading-screen soul animation (`soul_sequence`), scales by W/1280 and H/720 separately | Icon stretched horizontally | Same idea. Skip unless it looks bad. |
| `0x14045bfd0` | Pillarbox pass (bars when aspect is not 16:9), used for Bink movies (`movww/frpg_opening/title/goodending.bik`) | Movies 16:9 with bars: correct | none |
| Seath screen effect | Screen-space effect covers only the centre 16:9 (C) | Cosmetic | none |

## 3. Runtime plan

### 3.1 App (`opennative-src`), the main change
1. At launch, compute the internal size from the real display (landscape, full-screen view size including the cutout area):
   `H = 648 (Flip6) or 720 (default); W = round_to_even(H * viewW / viewH)`.
   - Flip6 2640x1080 -> **1584x648** (1.03 MP, +11% vs 1280x720).
   - S23 Ultra 3088x1440 -> **1544x720** (1.11 MP, +21%).
   - Native 2640x1080 = 2.85 MP (3.1x): GPU cost too high. Do not use it.
2. Put it in `container.screenSize`. The X server (`XServer(ScreenInfo(screenSize))`) and `wine explorer /desktop=shell,<WxH>` (`XServerScreen.kt:3907`, `PreInstallSteps.kt:114`) both follow. Custom sizes already work (`GeneralTab` custom dialog, only W > H is required).
3. Keep the renderer in "fit" mode. When the aspect matches, fit = full screen with no bars and no stretching. Make sure the game view uses the full display, including the cutout (`LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES`), or a few pixels of bar remain (RT).
4. Check that the touch overlay maps to X coordinates through `ViewTransformation` / screen size, not 1280x720 (no hard-coded 1280/720 found in `app/gamenative/dsr/`).
5. Height must stay >= 600, or the DLL must apply the 2.1 filter patch (`.text`).

### 3.2 Agent DLL (`mod/dinput8`), small and generic
The DLL needs no aspect math. The game reads the aspect from the render size, so the same DLL works on both phones.
1. Log once at boot: `GetSystemMetrics(SM_CXSCREEN/SM_CYSCREEN)`, init +0x34/+0x38 (`[0x141c6aee8]`), render size `[[0x141b68ec8]+0x6f0]`. All three must equal the X screen.
2. **Pin the display option to the desktop size.** On the game thread, as soon as `opt = [[0x141c8a530]+0x68]` is non-null (after the profile/sl2 loads):
   `opt+0xc4 = 2` (borderless); `opt+0xd0/+0xd4 = opt+0xd8/+0xdc = (dw, dh)`.
   This stops an old sl2 value (for example 1280x720 fullscreen, valid on the S23 Ultra list) from shrinking the swapchain back to 16:9.
   - The render size is fixed at boot (2.1), so a later mismatch would only rescale the swapchain. Pinning avoids that.
   - Trigger (RT): check whether `0x1402055c0` runs on title/load (log a hit). If it does not, call it once from the agent's game-thread hook after the write.
   - Alternative: set "Screen mode: Borderless" once in the in-game PC settings. It persists in the sl2. `DsrLauncher` can already decrypt the sl2 if an offline edit is preferred.
3. Optional, only if needed: the 800x600 filter patch (2.1), the title 1920-space fix (2.3), and the FOV clamp (2.2). All are `.text` writes. The DLL so far patched only `.rdata` and vtables, so check first that the anti-tamper tolerates `.text` writes (`BOX64_DYNAREC_DIRTY=2` notes).

## 4. Risks
- **CPU cost of the wider FOV.** The game main thread is the bottleneck (PORTING_LOG). The view frustum is 25-40% wider, so more objects pass culling and more draw calls are made. Expect a few FPS lost in open areas (Firelink, Undead Burg). Measure with `tools/bench.sh`. Fallback: FOV clamp (2.2) or a narrower internal aspect.
- **GPU cost:** +11% / +21% pixels at 1584x648 / 1544x720. It is small, but post-process (AO, DoF, motion blur) scales with it.
- **Saved option overrides:** see 3.2 step 2. If the option is not pinned, the S23 Ultra can silently return to 1280x720.
- **Window mode 1** at desktop size: the game window has a caption (`WS_CAPTION`), so the client area would be smaller than the desktop. Use borderless (2) or fullscreen (0).
- **HUD at the far edges:** HUD corners move to the screen corners (native behaviour). On the Flip6 the left/right corners sit under the thumbs or the cutout. The app's custom overlays (slots, stick) may need re-layout for 22:9.
- **Cutscenes:** real-time (`remo/`) are Hor+ (C). Bink movies have bars (S). The Seath effect is centre-only (C).
- **Title / loading screens:** may stretch horizontally (2.3, RT).
- **UI above 3840 px width breaks** (C). This does not apply here.

## 5. Test checklist (per phone)
1. Boot log: X screen = `GetSystemMetrics` = init +0x34/+0x38 = render size float2. Camera `[[[0x141c6e188]+0x10]+0x54]` = W/H.
2. Screenshot at the bonfire: full screen, no bars, circles look round (no stretch). Compare the horizontal FOV against a 1280x720 shot.
3. HUD: HP/stamina top-left at the corner, souls counter bottom-right, item slots / boss bar / lock-on reticle on target (tap-to-lock projection uses the render size).
4. Menus: menu bar, inventory, equipment, PC settings, yes/no dialog. All are 16:9-proportioned and not stretched. Taps hit the right items.
5. Title screen, "Press start", loading screen: note any stretching.
6. Opening movie (`frpg_opening.bik`): 16:9 with side bars. Real-time cutscene (for example the Asylum Demon intro): full width.
7. Change "Screen mode" in PC settings and restart. The size stays pinned.
8. Performance: `tools/bench.sh` at Firelink and the Undead Burg, 1280x720 vs the new size, same FPS cap and temperature.
9. Fold/unfold the Flip6 (if supported) and rotate: no crash, size unchanged.

## Sources
- PCGamingWiki, Dark Souls Remastered, Video (ultrawide Hor+, >4K UI bug, FOV fixes): https://www.pcgamingwiki.com/wiki/Dark_Souls_Remastered
- Steam "21:9 support" thread (HUD formatted for 21:9; intro 16:9; in-engine cutscenes 21:9): https://steamcommunity.com/app/570940/discussions/0/1694922345929611575
- Steam 2560x1080 thread (works; Seath effect centre-only): https://steamcommunity.com/app/570940/discussions/0/1697174779846737890
- Wine 9 virtual-desktop mode list (`win32u/sysparams.c`, `screen_sizes[]`): https://github.com/wine-mirror/wine/blob/wine-9.0/dlls/win32u/sysparams.c
- FOV tools (not needed, for reference): https://community.pcgamingwiki.com/files/file/1289-dark-souls-remastered-fov-fix/ , https://www.nexusmods.com/darksouls/mods/1063
- Scratch: decompiles from `re/ui/ghidra/dec.sh` (functions listed above).
