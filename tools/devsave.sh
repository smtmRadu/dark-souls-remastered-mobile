#!/bin/bash
# devsave.sh pull|push [NAME] : keep the development save (user 2026-10-15: the current save is the fixed save for
# controls / menu work). pull = phone -> saves_backup/DRAKS0005.<NAME>.sl2 ; push = that file -> phone (game stopped).
# Default NAME: dev-controls. Phone path: the Wine prefix's Documents/NBGI/DARK SOULS REMASTERED/<steam id>/.
export MSYS_NO_PATHCONV=1
P=com.remipelloux.gamenativecustom
D="$(cd "$(dirname "$0")/.." && pwd)"
NAME=${2:-dev-controls}; F="$D/saves_backup/DRAKS0005.$NAME.sl2"
SAVE=$(adb shell run-as $P find files/imagefs_shared -name DRAKS0005.sl2 2>/dev/null | tr -d '\r' | head -1)
[ -n "$SAVE" ] || { echo "save not found on phone"; exit 1; }
case "$1" in
  pull) adb exec-out run-as $P cat "$SAVE" > "$F" && md5sum "$F" && echo "pulled $SAVE";;
  push) adb shell am force-stop $P
        adb push "$(cygpath -w "$F")" /data/local/tmp/dev.sl2 >/dev/null && adb shell "run-as $P cp /data/local/tmp/dev.sl2 '$SAVE'" && echo "pushed $F";;
  *) echo "usage: devsave.sh pull|push [NAME]"; exit 2;;
esac
