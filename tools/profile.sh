#!/bin/bash
# profile.sh SECS : function-level CPU profile of the game's main thread via the in-game agent's sampler.
# The game must be in gameplay. Writes dsr_prof.go -> agent samples + unwinds the main thread ~1 kHz ->
# dsr_prof.txt. Moves the character meanwhile, then aggregates with tools/stackprof.py.
export MSYS_NO_PATHCONV=1; ADB="$LOCALAPPDATA/Microsoft/WinGet/Packages/Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe/platform-tools/adb.exe"
PKG=com.remipelloux.gamenativecustom; G=CustomGames/DarkSoulsRemastered; D="$(cd "$(dirname "$0")" && pwd)"; O="$D/out"; T=${1:-20}
"$ADB" shell "run-as $PKG sh -c 'rm -f $G/dsr_prof.txt; echo $T > $G/dsr_prof.go'"
for i in $(seq 1 $((T/10+1))); do "$ADB" shell "input swipe 277 778 277 560 4000; input swipe 1320 540 1750 540 700; input swipe 277 778 277 990 4000; input swipe 1750 540 1320 540 700"; done
for i in $(seq 1 30); do "$ADB" shell "run-as $PKG tail -1 $G/dsr_agent.log" | grep -q "prof: [0-9]* samples" && break; sleep 2; done
"$ADB" shell "run-as $PKG tail -2 $G/dsr_agent.log"
"$ADB" shell "run-as $PKG cat $G/dsr_prof.txt" | tr -d '\r' > "$O/prof_${2:-run}.txt"; wc -l "$O/prof_${2:-run}.txt"
