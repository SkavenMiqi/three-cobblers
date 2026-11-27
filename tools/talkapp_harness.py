"""Run the dedicated TalkApp LAN endpoint without opening the desktop app."""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from talkapp.harness_lan import HarnessHost
from talkapp.lan_pairing import local_address
from talkapp.storage import data_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path, help='只允许此工作目录中新建专用会话')
    parser.add_argument('--forget', action='store_true', help='解除以前绑定的手机')
    args = parser.parse_args()
    root = data_dir() / 'harness-host'
    root.mkdir(exist_ok=True)
    host = HarnessHost(root, local_address(), args.directory)
    try:
        if args.forget:
            host.forget()
        if not host.paired():
            import qrcode
            qr = qrcode.QRCode(border=2)
            qr.add_data(host.invitation())
            qr.print_ascii(tty=False, invert=True)
            print('请用 TalkApp 首页「Harness → 扫码连接」扫码，有效期 5 分钟。')
        print('Harness 后台正在运行；关闭此窗口即断开。', flush=True)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        host.close()


if __name__ == '__main__':
    main()
