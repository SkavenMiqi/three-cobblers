#!/usr/bin/env bash
set -euo pipefail
source /mnt/f/Works/Python/talkApp/tools/android_env.sh
test -d "$HOME/android-build"
mkdir -p "$ANDROID_HOME/cmdline-tools" "$TMPDIR" "$XDG_CACHE_HOME" "$GRADLE_USER_HOME"
archive="$HOME/android-build/commandlinetools-linux-11076708_latest.zip"
if [[ ! -x "$ANDROID_HOME/cmdline-tools/12.0/bin/sdkmanager" ]]; then
    curl -fL --retry 4 --connect-timeout 30 --max-time 900 -C - \
        https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -o "$archive"
    unzip -q -o "$archive" -d "$ANDROID_HOME/cmdline-tools"
    mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/12.0"
fi
# Buildozer 1.5 probes the legacy tools/bin location.
if [[ ! -e "$ANDROID_HOME/tools" ]]; then
    ln -s cmdline-tools/12.0 "$ANDROID_HOME/tools"
fi
# sdkmanager exits after reading the accepted licenses; yes may get SIGPIPE.
set +o pipefail
yes | sdkmanager --sdk_root="$ANDROID_HOME" --licenses
set -o pipefail
sdkmanager --sdk_root="$ANDROID_HOME" 'platform-tools' 'platforms;android-35' 'build-tools;35.0.0' 'ndk;25.2.9519653'
sdkmanager --sdk_root="$ANDROID_HOME" --list_installed
