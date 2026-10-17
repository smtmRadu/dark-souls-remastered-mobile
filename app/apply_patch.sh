#!/bin/bash
# apply_patch.sh [DIR]: get the Android app source = OpenNative (GPL-3) at the tested base commit + the DSR port patch.
# Then build: tools/build_agent.sh --release (copies the agent into the app assets), add the Box64 0.4.4 bionic
# package (see README), and run ./gradlew :app:assembleLegacyDebug in DIR (JDK 17).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
DIR=${1:-opennative-src}
BASE=6ff47dfd13f0db65be005430ec5dc78ca5b5997b
git clone https://github.com/RemiPelloux/OpenNative.git "$DIR"
git -C "$DIR" checkout -b dsr $BASE
git -C "$DIR" apply --whitespace=nowarn "$HERE/opennative-dsr.patch"
echo "OpenNative + DSR port ready in $DIR (branch dsr)"
