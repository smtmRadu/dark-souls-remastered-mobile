#!/bin/bash
# record_session.sh [NAME] : record a guided play session for one-batch debugging.
# Waits for the phone, then logs until stopped (Ctrl-C / kill):
#   out/rec_NAME/logcat.txt   app log (DSR tag: phases, loadout incl. 2H style, title taps)
#   out/rec_NAME/agent.log    agent log copy (menustate diffs: statelog 1), pulled every 10 s
#   out/rec_NAME/vNN.mp4      screen video in 3-minute chunks (1320x540), file time = chunk start
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")"
N=${1:-$(date +%m%d_%H%M)}
O=out/rec_$N; mkdir -p "$O"
P=com.remipelloux.gamenativecustom; G=CustomGames/DarkSoulsRemastered
adb wait-for-device
echo "phone connected $(date +%T)" | tee "$O/session.txt"
adb shell "run-as $P sh -c 'echo statelog 1 > $G/dsr_cmd.txt'"
adb logcat -c
adb logcat -v time -s DSR:I > "$O/logcat.txt" &
(
  i=0
  while true; do
    f=$(printf v%02d $i); echo "$f start $(date +%T)" >> "$O/session.txt"
    adb shell "screenrecord --time-limit 180 --size 1320x540 /data/local/tmp/rec.mp4"
    adb pull /data/local/tmp/rec.mp4 "$(cygpath -w "$O/$f.mp4")" >/dev/null
    i=$((i + 1))
  done
) &
while true; do
  adb shell "run-as $P sh -c 'grep -q \"statelog 1\" $G/dsr_cmd.txt 2>/dev/null || true; cat $G/dsr_agent.log'" > "$O/agent.log" 2>/dev/null
  t=$(adb shell dumpsys battery | grep '  temperature' | awk '{print $2}')
  echo "$(date +%T) battery $t" >> "$O/battery.txt"
  sleep 10
done
