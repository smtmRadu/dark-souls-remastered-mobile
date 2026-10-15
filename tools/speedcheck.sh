#!/bin/bash
# speedcheck.sh: hold the stick forward for exactly 4 s of real time, print distance walked (game units).
# Same FPS + same distance => same real-world speed. Compare runs with/without the tick patch.
export MSYS_NO_PATHCONV=1; ADB="$LOCALAPPDATA/Microsoft/WinGet/Packages/Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe/platform-tools/adb.exe"
pos() { "$ADB" shell run-as com.remipelloux.gamenativecustom sh /data/local/tmp/pos.sh | tr -d '\r\n'; }
for k in 1 2 3; do
  a=$(pos); "$ADB" shell input swipe 277 778 277 560 4000; b=$(pos); "$ADB" shell input swipe 277 778 277 990 4000
  python -c "import struct,math;f=lambda h:struct.unpack('<3f',bytes.fromhex(h));x=f('$a');y=f('$b');print('run %d: dist=%.2f'%($k,math.dist((x[0],x[2]),(y[0],y[2]))))"
done
