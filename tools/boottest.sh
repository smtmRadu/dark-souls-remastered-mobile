#!/bin/bash
# boottest.sh N : N cold starts to gameplay; after 20 s of moving, report alive/dead + agent log tail. Stability check for agent changes.
export MSYS_NO_PATHCONV=1; ADB="$LOCALAPPDATA/Microsoft/WinGet/Packages/Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe/platform-tools/adb.exe"
D="$(cd "$(dirname "$0")" && pwd)"; ok=0
for i in $(seq 1 $1); do
  "$ADB" shell "run-as com.remipelloux.gamenativecustom sh -c ': > CustomGames/DarkSoulsRemastered/dsr_agent.log'"
  r=$(bash "$D/bench.sh" boot 20 2>&1 | grep -m1 entered)
  pid=$("$ADB" shell pidof DarkSoulsRemastered.exe | tr -d '\r')
  echo "boot $i/$1: $r alive=${pid:-NO}"
  [ -n "$pid" ] && [ "$r" = "entered: GAMEPLAY" ] && ok=$((ok+1)) || "$ADB" shell "run-as com.remipelloux.gamenativecustom tail -3 CustomGames/DarkSoulsRemastered/dsr_agent.log"
done
echo "stable $ok/$1"
