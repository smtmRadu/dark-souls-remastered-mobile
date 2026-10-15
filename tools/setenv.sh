#!/bin/bash
# setenv.sh KEY=VAL ... | -KEY : set/remove env vars in the DSR container's envVars
export MSYS_NO_PATHCONV=1; ADB="$LOCALAPPDATA/Microsoft/WinGet/Packages/Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe/platform-tools/adb.exe"
PKG=com.remipelloux.gamenativecustom; C=files/imagefs/home/xuser-SHARED_PREFIX/.container
D="$(cd "$(dirname "$0")" && pwd)/out"; mkdir -p "$D"; F="$D/container.json"
"$ADB" shell run-as $PKG cat $C > "$F"
python - "$(cygpath -w "$F")" "$@" <<'PY'
import json,sys
f=sys.argv[1]; d=json.load(open(f,encoding='utf-8'))
env=dict(kv.split('=',1) for kv in d['envVars'].split())
for a in sys.argv[2:]:
    if a.startswith('-'): env.pop(a[1:],None)
    else: k,v=a.split('=',1); env[k]=v
d['envVars']=' '.join(f'{k}={v}' for k,v in env.items())
json.dump(d,open(f,'w',encoding='utf-8')); print(d['envVars'])
PY
"$ADB" push "$(cygpath -w "$F")" /data/local/tmp/container.json >/dev/null
"$ADB" shell "run-as $PKG sh -c 'cat /data/local/tmp/container.json > $C'"
