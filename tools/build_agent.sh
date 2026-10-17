#!/bin/bash
# build_agent.sh [--release] : build the in-game agent (mod/dinput8/dinput8.dll, mingw in WSL) and copy it into the
# app assets. Default = dev build (-DDSR_DEV: test commands such as "souls N"). --release leaves them out: use it for
# any build given to players.
D=$(cd "$(dirname "$0")/.." && pwd)
DEF=-DDSR_DEV; [ "$1" = --release ] && DEF=
wsl -e bash -lc "cd '$(wslpath "$D" 2>/dev/null || echo /mnt/c${D#/c})/mod/dinput8' && x86_64-w64-mingw32-gcc -O2 $DEF -shared -o dinput8.dll dinput8.c dinput8.def -static-libgcc -lwinmm -ldxguid" || exit 1
cp "$D/mod/dinput8/dinput8.dll" "$D/local/opennative-src/app/src/main/assets/dsr/dinput8.dll"
echo "agent built (${DEF:-release})"
