#!/bin/bash
# abtest.sh SECS "LABEL:+KEY=VAL,-KEY" ... : one bench per config (env edits via setenv.sh), then restore.
# Summary lines go to out/abtest.log. Compare cycles/frame (clock-independent) and FPS.
D="$(cd "$(dirname "$0")" && pwd)"; T=$1; shift; L="$D/out/abtest.log"; i=0; n=$#
for cfg in "$@"; do
  i=$((i+1)); lab=${cfg%%:*}; edits=${cfg#*:}
  undo=()
  IFS=',' read -ra E <<< "$edits"
  for e in "${E[@]}"; do [ -z "$e" ] && continue
    case $e in +*) kv=${e#+}; bash "$D/setenv.sh" "$kv" >/dev/null; undo+=("-${kv%%=*}");; -*) bash "$D/setenv.sh" "$e" >/dev/null;; esac
  done
  echo "[$i/$n] $lab" >> "$L"
  bash "$D/bench.sh" "ab_$lab" "$T" 2>&1 | grep -E "SUMMARY|timescale|cycles/frame|BOX64_DYNAREC" | sed -E "s/^/  $lab: /; s/ BOX64_(RCFILE|SYSINFO_[A-Z]*|X11GLX|NOBANNER|UNITYPLAYER|LOG|MMAP32)=[^ ]*//g" >> "$L"
  for u in "${undo[@]}"; do bash "$D/setenv.sh" "$u" >/dev/null; done
done
echo "done $n/$n" >> "$L"
