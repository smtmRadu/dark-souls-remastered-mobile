# Development process

The user reports issues. Claude fixes them, then tests them on the phone. Every round follows this loop. Claude must not ask the user to test each step by hand.

## The loop

1. **Collect.** Put every reported issue on the roadmap (`.track/vX.md`, status `in_progress`).
2. **Edit in a batch.** Fix all open items before you touch the phone. Never restart the app for one small edit.
3. **Build everything once.**
   - Agent DLL (`mod/dinput8`, mingw in WSL). Copy it to `opennative-src/app/src/main/assets/dsr/dinput8.dll`.
   - Menu layout: `python tools/patch_menu.py` → `tools/out/menu.drb.dcx`.
   - APK: `./gradlew :app:assembleLegacyDebug` (JDK 17) in `opennative-src`.
4. **Check the phone temperature.** Battery must be < 42 °C (`adb shell dumpsys battery`). If it is hotter, wait.
5. **Install, push, restart once.** Use `tools/batch_test.sh` or the same steps: install the APK, push `menu.drb.dcx`, force-stop, start.
6. **Verify every item with a screenshot.**
   - Take a screenshot with `python tools/shot.py NAME` (writes `tools/out/NAME.png` and `NAME_s.png`).
   - Look at each screenshot and compare it with the request.
   - Use the agent state log for menu states: write `statelog 1` to `dsr_cmd.txt` in the game folder, then read `dsr_agent.log`.
   - Use app logs for phases: `adb logcat -s DSR:I`.
7. **Fix what failed.** Fix the remaining failures in the next batch. Do not do one-off restarts.
8. **Report.** Give the user a short pass/fail list per item. Mention only what needs their eyes or hands.
9. **Document.** Update the roadmap status, `docs/ADDRESSES.md` (every new address), and the topic doc (`docs/CONTROLS.md`, `docs/ui/UI_RE.md`, ...).

## Rules

- **Batch, then one restart.** A restart takes minutes and heats the phone.
- **Screenshots are the proof.** Do not call a feature done until a screenshot (or log) shows it working.
- **Drive the game yourself when it is safe.** Use `adb shell input` taps, or the agent `tap X Y` command. Do not send input while the user is playing. Ask first, or wait until they hand the phone over.
- **Save game.** The user's current save is the dev save. Back it up with `tools/devsave.sh pull`. Restore it with `devsave.sh push` after tests that change it.
- **Title-screen coordinates** (2640x1080): Continue (270, 834), System (1845, 834). Check `tools/batch_test.sh` before tapping. Wait until the title list shows (screenshot) before tapping Continue: an early tap is taken as "Touch to start" and the script then waits forever.
- **Never write the game's `.text`.** The anti-tamper check kills the game about 2 s later. Patch `.data`, `.rdata` pointers or vtables only.
- **Git.** Commit and push only when the user asks. Push only docs, roadmap, scripts and mod source. Never push game files, saves or builds.
