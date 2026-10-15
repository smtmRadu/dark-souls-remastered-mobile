# OpenNative code map (for the DSR single-game fork)
Base: opennative-src/app/src/main/java/

- Start destination: ui/PluviaMain.kt:1154-1165 (LoginUser if no store creds) → hardcode Home/XServer.
- Store tabs: ui/enums/LibraryTab.kt visibleEntries (line 90) → LOCAL only. Prefs PrefManager.kt:1103-1137.
- FitGirl/Skidrow feeds: seeded from assets/opennative-provider-tabs.json via provider/ProviderDefaultTabs.kt; calls PluviaApp.kt:112-122, ProviderLibraryViewModel.kt:115 → remove.
- Store services/OAuth in AndroidManifest.xml:94-167 → remove.
- Custom import: utils/CustomGameImporter.kt; dest CustomGameScanner.kt:88-104; id file `.gamenative`; exe pick provider/ExecutableDiscovery.kt → set executablePath explicitly.
- Launch: PluviaMain onClickPlay 1245 → preLaunchApp 1444 → MainViewModel.launchApp 455 → XServer route (ui/screen/xserver/XServerScreen.kt; setupXEnvironment 3742).
- Container: com/winlator/container/Container.java (+ ContainerData, ContainerUtils.applyToContainer). Defaults: core/DefaultVersion.java, ContainerUtils.setContainerDefaults 48-96 (Adreno → bionic, proton-10.0-arm64ec-2, Turnip v26.2.0 R4, DXVK 2.4.1-gplasync). Already FEXCore + 1280x720.
- GOTCHA: Container.java:41 DEFAULT_GRAPHICS_DRIVER is static final copy; hardcoded /data/data/app.gamenative paths at 48-56 if applicationId changes.
- Direct launch intent exists: ${applicationId}.LAUNCH_GAME, extras app_id/game_source/container_config (utils/IntentLaunchManager.kt; MainActivity.kt:296-363).
- Saves: files/imagefs/home/xuser-<id>/.wine/drive_c/users/xuser/Documents/NBGI/DARK SOULS REMASTERED; useSharedWinePrefix default true (SHARED_PREFIX).
- Touch controls: assets/inputcontrols/profiles/controls-N.icp (JSON); container extra profileId; view com/winlator/widget/InputControlsView.java.
