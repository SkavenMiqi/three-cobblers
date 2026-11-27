"""Public setup instructions readable over an already-authorized ADB link."""
from pathlib import Path

FILENAME = 'harness-first-setup.txt'
BUNDLE = 'talkapp-harness-backend.zip'
BUNDLE_ASSET = 'talkapp-harness-backend.harnessbundle'
ADB_READ = f'adb shell run-as org.skaven.talkapp cat files/{FILENAME}'

FIRST_SETUP = f'''TalkApp · Harness 首次连接清单（版本 3）

1. 确认手机和电脑在同一局域网、TalkApp 已打开、ADB 已连接到用户授权的手机（adb devices -l）。任何能运行 ADB 的 Harness 都可协助首次设置。若电脑和手机已配对，优先复用原后台和配对，跳过无线调试和扫码。
2. 确认用户要用的执行后台和工程目录。手机附带的是 OpenCode V2 适配器；其他执行后台须有兼容的 TalkApp 适配器。使用 OpenCode 时，打开 OpenCode 并用 opencode api get /api/info 确认本机服务可用。Windows 桌面版如未加入 PATH，可使用安装目录 resources 下的 opencode-cli.exe。
3. 电脑没有后台时，在电脑上直接提取手机附带的压缩包（用 cmd、bash，或任何保留原始字节的方式重定向；多台设备时用 adb -s <序列号> 选定手机）：
   adb exec-out run-as org.skaven.talkapp cat files/{BUNDLE} > {BUNDLE}
   python -m zipfile -e {BUNDLE} talkapp-harness
   cd talkapp-harness
   使用 Python 3.10 或更新版本，建虚拟环境并用对应的 Python 安装依赖：python -m pip install -r requirements-harness.txt。已有可用环境就复用，不需要 PC 版 TalkApp。
4. 运行 python -X utf8 -u tools/talkapp_harness.py "用户确认的工程目录"，保留终端运行。已有配对会直接等待重连；新配对时让用户在手机首页点「Harness → 扫码连接」，扫描终端显示的二维码。后台只监听局域网，不开放公网端口，不修改 OpenCode 权限。
5. 看到「已连接 · 自动配置完成」后回到普通对话。可在电脑的 TalkApp 数据目录（默认 ~/.talkapp）的 harness-host 文件夹核对 client-config.json 和 chat-*.json 的更新时间。普通对话的近期文字会被动同步，不调用电脑上的模型；临时对话不做同步。验证后可关无线调试，日常只走局域网。
'''


def publish(root):
    """Export the bundled backend and fixed instructions, without user data."""
    bundle = Path(__file__).with_name(BUNDLE_ASSET)
    if bundle.is_file():
        _publish_file(root / BUNDLE, bundle.read_bytes())
    _publish_file(root / FILENAME, FIRST_SETUP.encode('utf-8'))


def _publish_file(path, content):
    try:
        if path.read_bytes() == content:
            return
    except FileNotFoundError:
        pass
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(content)
    temporary.replace(path)
