#!/usr/bin/env bash
set -euo pipefail
export HOME=/home/skaven
test -d "$HOME"
mkdir -p "$HOME/android-build" "$HOME/.cache/pip" "$HOME/android-build/tmp"
python3 -m venv "$HOME/android-build/venv"
source "$HOME/android-build/venv/bin/activate"
python -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple 'pip<26' 'setuptools<71' wheel 'buildozer==1.5.0' 'Cython==0.29.37'
java -version
buildozer --version
