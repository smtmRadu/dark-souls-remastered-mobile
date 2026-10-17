#!/bin/bash
# play.sh [--install] : (optionally install the fresh APK) cold start -> ✓ until DSR phase GAMEPLAY. For control tests.
export MSYS_NO_PATHCONV=1; ADB="$LOCALAPPDATA/Microsoft/WinGet/Packages/Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe/platform-tools/adb.exe"
D="$(cd "$(dirname "$0")" && pwd)"; P=com.remipelloux.gamenativecustom
ok() { "$ADB" shell input swipe 705 837 705 837 90; }
phase() { "$ADB" logcat -d -s DSR:I | grep -o 'phase [A-Z_]* -> [A-Z_]*' | tail -1 | awk '{print $4}'; }
"$ADB" shell am force-stop $P; sleep 1
[ "$1" = --install ] && "$ADB" install -r "$(cygpath -w "$D/../local/opennative-src/app/build/outputs/apk/legacy/debug/app-legacy-debug.apk")" | tail -1 && sleep 3
"$ADB" logcat -c; "$ADB" shell am start -n $P/app.gamenative.MainActivityAliasDefault >/dev/null
for i in $(seq 1 60); do sleep 3; [ "$(phase)" = TITLE ] && break; done; sleep 6
for i in $(seq 1 10); do ok; sleep 4; p=$(phase); [ "$p" = GAMEPLAY ] && break; [ "$p" = LOADING ] && { sleep 8; [ "$(phase)" = GAMEPLAY ] && break; }; done
echo "phase: $(phase)"
