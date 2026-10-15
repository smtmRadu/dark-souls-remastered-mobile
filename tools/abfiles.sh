#!/bin/bash
# abfiles.sh SECS "LABEL:file=content;-file" ... : like abtest.sh but toggles agent flag files in the game folder.
export MSYS_NO_PATHCONV=1; ADB="$LOCALAPPDATA/Microsoft/WinGet/Packages/Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe/platform-tools/adb.exe"
D="$(cd "$(dirname "$0")" && pwd)"; T=$1; shift; L="$D/out/abtest.log"; i=0; n=$#; G=CustomGames/DarkSoulsRemastered
for cfg in "$@"; do
  i=$((i+1)); lab=${cfg%%:*}; edits=${cfg#*:}
  IFS=';' read -ra E <<< "$edits"
  for e in "${E[@]}"; do [ -z "$e" ] && continue
    case $e in -*) "$ADB" shell "run-as com.remipelloux.gamenativecustom rm -f $G/${e#-}";;
      *) "$ADB" shell "run-as com.remipelloux.gamenativecustom sh -c 'echo ${e#*=} > $G/${e%%=*}'";; esac
  done
  echo "[$i/$n] $lab" >> "$L"
  bash "$D/bench.sh" "ab_$lab" "$T" 2>&1 | grep -E "SUMMARY|timescale|cycles/frame" | sed "s/^/  $lab: /" >> "$L"
  "$ADB" shell "run-as com.remipelloux.gamenativecustom grep -E 'lod:|gov:' $G/dsr_agent.log | tail -2" | sed "s/^/  $lab: /" >> "$L"
done
echo "done $n/$n" >> "$L"
