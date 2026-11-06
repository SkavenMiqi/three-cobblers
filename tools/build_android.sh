#!/usr/bin/env bash
set -euo pipefail
source /mnt/f/Works/Python/talkApp/tools/android_env.sh
SOURCE=/mnt/f/Works/Python/talkApp
BUILD="$HOME/android-build/project"
test -d "$SOURCE/talkapp"
mkdir -p "$BUILD" "$TMPDIR" "$XDG_CACHE_HOME" "$GRADLE_USER_HOME"
# Compile on ext4 inside the F:-backed VHD, avoiding NTFS symlink/case issues.
rsync -a --exclude .git --exclude fitness --exclude fitness-original --exclude backups --exclude .venv --exclude .buildozer \
    --exclude bin --exclude __pycache__ --exclude '*.zip' "$SOURCE/" "$BUILD/"
export APP_ANDROID_SDK_PATH="$ANDROID_HOME"
export APP_ANDROID_NDK_PATH="$ANDROID_NDK_HOME"
export APP_ANDROID_NDK=25c
export APP_ANDROID_ANT_PATH=/usr/share/ant
if [[ -d "$HOME/android-build/p4a-local/pythonforandroid" ]]; then
    export APP_P4A_SOURCE_DIR="$HOME/android-build/p4a-local"
fi
if curl -s --proxy http://127.0.0.1:7890 --connect-timeout 2 --max-time 3 -I https://github.com >/dev/null 2>&1; then
    export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Dhttp.proxyHost=127.0.0.1 -Dhttp.proxyPort=7890 -Dhttps.proxyHost=127.0.0.1 -Dhttps.proxyPort=7890"
fi
cd "$BUILD"
buildozer -v android "${1:-debug}"
if [[ -d bin ]]; then
    mkdir -p "$SOURCE/bin"
    rsync -a bin/ "$SOURCE/bin/"
fi
