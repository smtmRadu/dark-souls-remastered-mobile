#!/bin/bash
# bench.sh LABEL SECONDS : cold start -> menu ✓ until DSR phase GAMEPLAY -> log FPS/clocks/temps every 10 s
export MSYS_NO_PATHCONV=1; ADB="$LOCALAPPDATA/Microsoft/WinGet/Packages/Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe/platform-tools/adb.exe"
D="$(cd "$(dirname "$0")" && pwd)"; mkdir -p "$D/out"; OUT="$D/out/bench_$1.log"; T=${2:-180}; : > "$OUT"
ok() { "$ADB" shell input swipe 705 837 705 837 90; }
phase() { "$ADB" logcat -d -s DSR:I | grep -o 'phase [A-Z_]* -> [A-Z_]*' | tail -1 | awk '{print $4}'; }
"$ADB" shell am force-stop com.remipelloux.gamenativecustom; sleep 2; "$ADB" logcat -c
"$ADB" shell am start -n com.remipelloux.gamenativecustom/app.gamenative.MainActivityAliasDefault >/dev/null
for i in $(seq 1 60); do sleep 4; p=$(phase); [ "$p" = TITLE ] && break; done
for i in $(seq 1 12); do ok; sleep 4; p=$(phase); [ "$p" = GAMEPLAY ] && break; [ "$p" = LOADING ] && { sleep 8; p=$(phase); [ "$p" = GAMEPLAY ] && break; }; done
echo "entered: $(phase)" | tee -a "$OUT"; sleep 10; "$ADB" logcat -c
temps() { "$ADB" shell 'for z in /sys/class/thermal/thermal_zone*; do case $(cat $z/type) in xo-therm|battery|cpu-1-2-0|gpuss-0) printf "%s=%s " $(cat $z/type) $(( $(cat $z/temp)/1000 ));; esac; done'; }
# ~10 s of play per sample: walk forward/back with the stick, turn the camera (no static scene)
move() { "$ADB" shell "input swipe 277 778 277 560 4000; input swipe 1320 540 1750 540 700; input swipe 277 778 277 990 4000; input swipe 1750 540 1320 540 700"; }
for i in $(seq 1 $((T/10))); do
  move
  f=$("$ADB" logcat -d -s DSRFPS:I | grep -o '[0-9.]*$' | tr '\n' ' '); "$ADB" logcat -c
  echo "$(date +%T) fps=[$f] max7=$(( $("$ADB" shell cat /sys/devices/system/cpu/cpu7/cpufreq/scaling_max_freq)/1000 )) max2=$(( $("$ADB" shell cat /sys/devices/system/cpu/cpu2/cpufreq/scaling_max_freq)/1000 )) $(temps)" | tee -a "$OUT"
done
python - "$(cygpath -w "$OUT")" <<'PY'
import sys,re
v=[float(x) for l in open(sys.argv[1]) for g in re.findall(r'fps=\[([^\]]*)\]',l) for x in g.split()]
v=sorted(x for x in v if x>1)
if v: print(f"SUMMARY N={len(v)} avg={sum(v)/len(v):.1f} p10={v[len(v)//10]:.1f} min={v[0]:.1f} >=28: {sum(x>=28 for x in v)/len(v):.0%}")
PY
bash "$D/timescale.sh" 10 | tee -a "$OUT"
# clock-independent efficiency: game-process CPU cycles per rendered frame (compare flags on a hot or cool phone)
P0=$("$ADB" shell pidof DarkSoulsRemastered.exe | awk '{print $1}' | tr -d ''); "$ADB" logcat -c
cyc=$("$ADB" shell "simpleperf stat --app com.remipelloux.gamenativecustom -p $P0 -e cpu-cycles --duration 10 2>/dev/null" | awk '/cpu-cycles/{gsub(",","",$1); print $1}')
fr=$("$ADB" logcat -d -s DSRFPS:I | grep -o '[0-9.]*$' | awk '{s+=$1;n++} END{if(n) print s/n*10; else print 0}')
python -c "c=float('${cyc:-0}');f=float('${fr:-0}');print('cycles/frame=%.1fM (cycles=%.2fG frames=%.0f)'%(c/f/1e6 if f else 0,c/1e9,f))" | tee -a "$OUT"
P=$("$ADB" shell pidof DarkSoulsRemastered.exe | awk '{print $1}' | tr -d '\r')
"$ADB" shell "simpleperf record --app com.remipelloux.gamenativecustom -p $P --duration 8 -o /data/local/tmp/b.data >/dev/null 2>&1; simpleperf report -i /data/local/tmp/b.data --sort symbol 2>/dev/null | grep -E 'cleanDB|FindDynablock|MarkRange'" | tee -a "$OUT"
"$ADB" shell "run-as com.remipelloux.gamenativecustom cat /proc/$P/environ" | tr '\0' '\n' | grep -E '^BOX64_' | tr '\n' ' ' | tee -a "$OUT"; echo | tee -a "$OUT"
