"""Android setup guide and pairing for the Harness endpoint."""
import threading

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from . import harness_lan, theme
from .harness_setup import FIRST_SETUP, ADB_READ
from .storage import data_dir


def open_harness(view):
    from .ui import button, label

    root = data_dir() / 'harness-phone'
    root.mkdir(exist_ok=True)
    peer = root / 'lan-computer.json'
    body = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(6))
    popup = Popup(title='连接 Harness · 首次使用', content=body, size_hint=(.96, .88))
    scroll = ScrollView(do_scroll_x=False)
    guide = BoxLayout(orientation='vertical', spacing=dp(12), size_hint_y=None)
    guide.bind(minimum_height=guide.setter('height'))
    scroll.add_widget(guide)
    body.add_widget(scroll)

    def paragraph(text):
        item = label(text, size_hint_y=None)
        item.bind(texture_size=lambda w, size: setattr(w, 'height', max(dp(36), size[1] + dp(12))))
        guide.add_widget(item)
        return item

    paragraph('1. 首次连接，请让电脑上的 Harness 通过安卓无线调试连上手机，直接读取首次连接清单。手机也附带了轻量后台，电脑可直接提取，不用你复制清单或安装 PC 版 TalkApp。')
    paragraph('2. 电脑显示配对二维码后，点「扫码连接」。扫码后手机会自动发送协作清单，后台自行适配。显示「自动配置完成」后，可关闭无线调试，回到原对话继续聊天。')
    details = paragraph('电脑端读取命令（当前调试版）：\n' + ADB_READ + '\n\n' + FIRST_SETUP)
    details.opacity = 0
    guide.remove_widget(details)

    def toggle_details():
        if details.parent:
            guide.remove_widget(details)
            detail_button.text = '查看首次配置清单'
        else:
            details.opacity = 1
            guide.add_widget(details)
            detail_button.text = '收起首次配置清单'

    detail_button = button('查看首次配置清单', toggle_details, size_hint_y=None, height=dp(40))
    guide.add_widget(detail_button)
    status = paragraph('请先按上面的步骤准备，再扫码。' if not peer.is_file() else '正在检查已配对的电脑…')
    pending = False

    def work(fn, done, failed=None):
        nonlocal pending
        if pending:
            return
        pending = True
        scan.disabled = True

        def worker():
            try:
                value, ok = fn(), True
            except (OSError, ValueError, KeyError) as exc:
                value, ok = exc, False

            def finish(_):
                nonlocal pending
                pending = False
                if not popup.parent or view.closed:
                    return
                if ok:
                    done(value)
                elif failed:
                    failed(value)
                scan.disabled = False

            Clock.schedule_once(finish)

        threading.Thread(target=worker, daemon=True).start()

    def refresh(*_):
        if not pending and popup.parent and peer.is_file():
            def ready(_):
                status.text = '已连接 · 自动配置完成，可以回到原对话继续聊天。'
                status.color = theme.LED_GREEN
                view.set_harness_status(True)
                view.harness_observe_ack = None
                view.sync_current_harness()

            def unready(error):
                missing = isinstance(error, harness_lan.HostUnavailable)
                view.set_harness_status(None if missing else False)
                status.text = str(error) if isinstance(error, ValueError) else '无法连接电脑后台。'
                status.color = theme.TEXT_MUTED if missing else theme.DANGER

            status.text = '正在把协作清单发给 Harness 并检查配置…'
            work(lambda: harness_lan.configure(root), ready, unready)

    def scan_code():
        if pending or not view.android:
            return
        from .qr_scan_view import scan_qr

        def found(code):
            if not popup.parent:
                return

            def pair():
                harness_lan.pair(root, code)

            def failed(error):
                if isinstance(error, OSError):
                    status.text = '已识别二维码，但找不到电脑后台。请检查局域网和电脑后台。'
                    status.color = theme.TEXT_MUTED
                else:
                    status.text = '已识别二维码，但配对未通过。请使用新的后台二维码。'
                    status.color = theme.DANGER

            work(pair, lambda _: Clock.schedule_once(refresh), failed)

        scan_qr(harness_lan.PREFIX, found, lambda error: setattr(status, 'text', error))

    actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
    scan = button('扫码连接', scan_code, accent=True)
    for item in (scan, button('关闭', popup.dismiss)):
        actions.add_widget(item)
    body.add_widget(actions)
    popup.open()
    Clock.schedule_once(refresh)
