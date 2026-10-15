#!/bin/bash
# timescale.sh [secs]: game play-time advance / real time (1.00 = real speed)
export MSYS_NO_PATHCONV=1; ADB="$LOCALAPPDATA/Microsoft/WinGet/Packages/Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe/platform-tools/adb.exe"
pt() { "$ADB" shell run-as com.remipelloux.gamenativecustom sh /data/local/tmp/ts.sh | tr -d '\r'; }
a=$(pt); t0=$(date +%s%3N); sleep ${1:-10}; b=$(pt); t1=$(date +%s%3N)
awk -v g=$((b-a)) -v r=$((t1-t0)) 'BEGIN{printf "game_ms=%d real_ms=%d timescale=%.2f\n",g,r,g/r}'
