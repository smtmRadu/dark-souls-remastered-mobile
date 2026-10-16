#!/bin/bash
# batch_test.sh : one game boot that checks a whole batch of UI changes (POLICY 2026-10-15: batch, then verify once).
# Installs the APK, pushes tools/out/menu.drb.dcx + tools/out/assets/ui/*.png, then walks title -> title System (Back)
# -> Continue -> gameplay -> menu bar -> System -> Options -> back -> Inventory -> item menu, one screenshot per step
# (out/bt_<step>_s.png). Phone coordinates for the Flip6 (2640x1080 landscape).
export MSYS_NO_PATHCONV=1
D="$(cd "$(dirname "$0")" && pwd)"; cd "$D"
P=com.remipelloux.gamenativecustom; G=CustomGames/DarkSoulsRemastered
phase() { adb logcat -d -s DSR:I | grep -o 'phase [A-Z_]* -> [A-Z_]*' | tail -1 | awk '{print $4}'; }
tap() { adb shell input swipe "$1" "$2" "$1" "$2" 90; sleep "${3:-3}"; }
shot() { python shot.py "bt_$1" 1400 >/dev/null; echo "shot bt_$1 (phase $(phase))"; }

adb shell am force-stop $P
[ "$1" = --no-install ] || adb install -r "$(cygpath -w ../opennative-src/app/build/outputs/apk/legacy/debug/app-legacy-debug.apk)" | tail -1
adb push "$(cygpath -w out/menu.drb.dcx)" /data/local/tmp/menu.drb.dcx >/dev/null
adb shell run-as $P cp /data/local/tmp/menu.drb.dcx $G/menu/menu.drb.dcx
[ -f out/menu_2.tpf.dcx ] && adb push "$(cygpath -w out/menu_2.tpf.dcx)" /data/local/tmp/m2.dcx >/dev/null && adb shell run-as $P cp /data/local/tmp/m2.dcx $G/menu/menu_2.tpf.dcx   # dark splash (dark_splash.py)
for f in out/assets/ui/*.png; do
  adb push "$(cygpath -w "$f")" /data/local/tmp/ui.png >/dev/null
  adb shell run-as $P cp /data/local/tmp/ui.png "$G/dsr_assets/ui/$(basename "$f")"
done
adb logcat -c; adb shell am start -n $P/app.gamenative.MainActivityAliasDefault >/dev/null
for i in $(seq 1 60); do sleep 3; [ "$(phase)" = TITLE ] && break; done; sleep 8
shot title_start
tap 1320 900 5; shot title_list
tap 1845 834 5; shot title_system          # System entry: Back must show
tap 1000 350 5; shot title_options          # title System -> Options by touch (mouse click path)
tap 2435 965 4; tap 2435 965 4; shot title_back   # Back x2 -> title list
tap 270 834 4                               # Continue (title row spread over 22:9)
for i in $(seq 1 40); do sleep 3; [ "$(phase)" = GAMEPLAY ] && break; done; sleep 12
shot gameplay
hold() { adb shell input motionevent DOWN $1 $2; adb shell input motionevent MOVE $1 $(( $2 - 40 )); adb shell input motionevent MOVE $(( $1 - 10 )) $(( $2 - 130 )); sleep 0.4; shot "$3"; adb shell input motionevent UP $(( $1 - 10 )) $(( $2 - 130 )); sleep 2; }
hold 2012 878 parry_held                    # Block: slide up = parry (thumb icon, ember pulse)
hold 2342 841 heavy_held                    # Attack: slide up = heavy attack
tap 2389 135 3; shot menubar                 # app Menu button: HUD hidden
tap 160 886 3; shot system                  # System tab
tap 1000 350 4; shot options                 # Options row
tap 2435 965 3; shot options_back
tap 1000 661 4; shot pcsettings              # PC settings row (Key settings hidden: row 4 of 5)
tap 2435 965 3; shot pc_back                 # Back: no leftover ◀ ▶
tap 1000 765 3; shot quit_box               # Quit Game: OK / Cancel box (F05)
tap 1513 965 3; shot quit_cancel            # Cancel
tap 160 250 3; shot inventory               # Inventory tab
adb shell input swipe 1000 800 1000 450 400; sleep 2; shot inv_swiped   # swipe: steps only, no selection jump
tap 1000 420 3; shot itemmenu               # first item row -> item command menu
tap 2435 965 3; tap 2435 965 3; tap 2435 965 3; shot closed
adb logcat -d -s DSR:I | grep -iE "title|governor" | tail -8
adb shell run-as $P "grep -iE 'menuhud|title' $G/dsr_agent.log" | tail -5
