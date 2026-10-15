# Dark Souls Remastered on Android: Dedicated APK + Mobile-First Mod

Target device: **Galaxy Z Flip6**, Snapdragon 8 Gen 3 for Galaxy, Adreno 750.
Game source: your **legitimate Steam copy**. The game starts through the real Steam client inside the APK.

## Goal
- One dedicated "Dark Souls" APK. No Winlator or GameNative install. You open it and play.
- Controls built for touch, not a controller mapped onto the screen:
  - Tap an enemy to lock on (no R3).
  - Swap items directly from a touch item bar (no menu walking).
  - HUD moved away from the thumb zones.
- Smooth play on the Flip6: about 30 FPS locked at roughly 720p–900p, tuned against heat.

## Why it is not a "native ARM" build
DSR is a closed x86-64 DirectX 11 binary. Re-compiling it for ARM without source code is not practical.
Instead the APK bakes in a hidden translation layer, tuned for this one game:

| Layer | What it does |
|---|---|
| Box64 | Translates x86-64 code to ARM64 at runtime |
| Wine | Provides the Windows API |
| DXVK | Turns DirectX 11 into Vulkan |
| Mesa Turnip | Open-source Vulkan driver for the Adreno 750 |

## How these mods take over a game (what people use now)
1. **Asset swaps:** new models and textures, same game logic.
2. **Pass-through mods:** two games run at once, synced by camera and events (Minecraft in GTA 5).
3. **Mechanic transplants:** game functions are hooked and replaced.
   - Mario in Elden Ring (`er-mario`) uses the `me3` mod loader plus `libsm64`, Super Mario 64's movement code built as a library.
4. **Full rebuilds:** systems are decompiled and rewritten. AI cuts this from years to months.

The AI part is Claude Code plus the `universal-modder` skills. Ghidra, x64dbg and Cheat Engine are wired in over MCP, so the agent decompiles, hooks and tests in a loop.

## Tool stack

### Reverse engineering (Victus)
- **Ghidra** with **GhidraMCP** or **ReVa**: decompile the game binary; Claude drives it over MCP.
- **x64dbg** with its MCP plugin: live debugging, breakpoints, stepping.
- **Cheat Engine** with an MCP server: find live values (lock-on target, equipped slots) and trace what writes them.
- **RenderDoc**: capture a frame to see how the HUD is drawn.
- **JPEXS FFDec**: edit the Scaleform `.gfx` HUD and menu files in `menu/`.
- **Smithbox / SoulsFormats**: unpack and edit FromSoftware game data (parameters, menus, layouts).

### Mod (C++)
- **me3** mod loader. It supports DSR and runs under Wine and Linux as well as Windows.
- **MinHook** for function hooks.
- **Byte-pattern scanning**, so the mod finds functions even after game updates.
- **Dear ImGui** as an optional debug overlay while developing.

### Android APK
- **Box64, Wine, DXVK and Turnip**, packaged the way Winlator does it (Winlator is LGPL).
- **Kotlin + Android NDK** for the app shell, launcher and touch layer.
- **A local socket** carrying commands from the touch layer to the mod DLL.
- **The real Steam client inside the APK.** Log in once; the game starts with its normal Steam check.

## Phases

### Phase 1: Reverse engineering (Victus, on claude20)
- [ ] Install Ghidra + GhidraMCP, x64dbg + MCP plugin, Cheat Engine + MCP server.
- [ ] **Lock-on:** find the current-target pointer, the target-selection function, and the enemy list with world positions.
- [ ] **Equipment:** find the equip and swap functions for weapon, spell and item slots.
- [ ] **Input:** find where the game reads input, so it can accept commands directly.
- [ ] **HUD:** map the `menu/*.gfx` files to the on-screen elements.
- [ ] Write down offsets and byte patterns in `RE_NOTES.md`.

### Phase 2: The mod (me3 code mod, C++)
- [ ] **Tap to lock on:** project every enemy onto the screen, pick the one nearest the tap, and call the game's own lock-on with that target.
- [ ] **Direct item swap:** tapping an item calls the game's own equip function.
- [ ] **Command channel:** a local socket that accepts `lock x y`, `equip slot N`, `roll`, `attack`, and so on.
- [ ] **Mobile HUD:** weapons and items move to the top corners, clear of the thumb zones.
- [ ] Test everything on the PC first.

### Phase 3: The dedicated APK
- [ ] Bundle Box64, Wine, DXVK and Turnip in a single "Dark Souls" app, with no generic menus.
- [ ] Bundle the Steam client and a first-run setup: Steam login, then the game files are copied from your own install.
- [ ] **Touch layer:** movement stick, camera swipe, tap-to-lock, swipe-to-roll, and an item bar that sends commands to the mod.
- [ ] **Flip6 tuning:** 30 FPS locked, resolution, DXVK settings, heat profile.

### Phase 4: Polish
- [ ] Haptics, a layout editor for the controls, and battery/heat profiles.
- [ ] Optional 60 FPS mode at lower settings.

## Ground rules
- Use the legitimate Steam copy only. Never share game files; the APK stays private.
- Play offline. DLL mods online risk a ban.

## References
- universal-modder (AI game modding skills): https://github.com/rehan-remade/universal-modder
- GhidraMCP: https://github.com/LaurieWired/GhidraMCP
- ReVa: https://github.com/cyberkaida/reverse-engineering-assistant
- x64dbg MCP: https://mcpservers.org/vi/servers/Wasdubya/x64dbgMCP
- Cheat Engine MCP: https://github.com/crain99/ce-mcp
- me3 mod loader: https://github.com/garyttierney/me3
- ModEngine2 (predecessor): https://github.com/soulsmods/ModEngine2
- Dark-Souls-1-Overhaul (DSR hook DLL): https://github.com/metal-crow/Dark-Souls-1-Overhaul
- DSR-Gadget (DSR memory layout): https://github.com/JKAnderson/DSR-Gadget
- Winlator: https://github.com/brunodev85/winlator
- Mario in Elden Ring (er-mario): https://unwire.hk/2026/10/05/elden-ring-mario-64-mod-er-mario-2/fun-tech/
- DSR HUD reposition mod (proof that HUD edits work): https://www.nexusmods.com/darksoulsremastered/mods/1071
- How the AI mashups work: https://www.mindstudio.ai/blog/ai-game-mashups-mods
