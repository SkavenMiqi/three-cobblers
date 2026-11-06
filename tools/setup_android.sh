#!/usr/bin/env bash
set -euo pipefail
# Run as root inside the F:\AndroidBuild-backed TalkApp-Build distro.
python3 - <<'PY'
from pathlib import Path
p = Path('/etc/apt/sources.list')
s = p.read_text()
s = s.replace('http://archive.ubuntu.com/ubuntu', 'https://mirrors.tuna.tsinghua.edu.cn/ubuntu')
s = s.replace('http://security.ubuntu.com/ubuntu', 'https://mirrors.tuna.tsinghua.edu.cn/ubuntu')
p.write_text(s)
PY
apt-get -o Acquire::ForceIPv4=true update
DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::ForceIPv4=true install -y --no-install-recommends \
  openjdk-17-jdk-headless python3-venv python3-pip python3-dev build-essential \
  git zip unzip autoconf automake libtool pkg-config zlib1g-dev libncurses5-dev \
  libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev libltdl-dev ccache rsync curl ant
runuser -u skaven -- bash /mnt/f/Works/Python/talkApp/tools/setup_android_user.sh
