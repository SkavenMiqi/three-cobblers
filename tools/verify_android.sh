#!/usr/bin/env bash
set -euo pipefail
source /mnt/f/Works/Python/talkApp/tools/android_env.sh
java -version
javac -version
python --version
buildozer --version
cython --version
adb version
"$ANDROID_HOME/build-tools/35.0.0/aapt2" version
"$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/clang" --version
test -f "$ANDROID_HOME/platforms/android-35/android.jar"
python -m pip check
printf '\nANDROID_TOOLCHAIN_OK\nSDK=%s\nNDK=%s\nGRADLE_CACHE=%s\n' "$ANDROID_HOME" "$ANDROID_NDK_HOME" "$GRADLE_USER_HOME"
df -h "$HOME/android-build"
