"""Pairing dialogs for the desktop host and Android client."""
import threading
from io import BytesIO

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.image import Image as CoreImage
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.utils import platform

from . import lan_opencode, lan_pairing
from .storage import data_dir


def open_pairing(view):
    from .ui import button, field, label

    root = data_dir()
    mobile = platform == 'android'
    body = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8), size_hint_y=None)
    body.bind(minimum_height=body.setter('height'))
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(body)
    popup = Popup(title='局域网设备配对', content=scroll, size_hint=(.94, .88), auto_dismiss=False)
    desktop_tip = '电脑和手机需在同一局域网。开启同步后，两端将交换普通聊天历史和图片。'
    mobile_tip = '扫描电脑的配对二维码，或粘贴配对串。开启同步后将共享普通聊天历史和图片。'
    help_text = label(mobile_tip if mobile else desktop_tip, size_hint_y=None, height=dp(76))
    body.add_widget(help_text)
    status = label('', size_hint_y=None, height=dp(72))
    body.add_widget(status)

    def action(caption, fn):
        item = button(caption, fn, size_hint_y=None, height=dp(42))
        body.add_widget(item)
        return item

    def auto_caption():
        return '启动时自动同步：' + ('开' if lan_pairing.auto_sync(root, mobile) else '关')

    def clear_auto_sync():
        lan_pairing.set_auto_sync(root)
        auto_button.text = auto_caption()

    def delegate_caption():
        return '自动委派 OpenCode：' + ('开' if lan_opencode.enabled(root, mobile) else '关')

    def toggle_delegate():
        try:
            if not peer.is_file():
                status.text = '请先完成设备配对。'
                return
            enabled = not lan_opencode.enabled(root, mobile)
            lan_opencode.set_enabled(root, enabled)
            delegate_button.text = delegate_caption()
            status.text = ('已开启。两端开启同步和自动委派后，可自动派单，无需在电脑确认。'
                           if enabled else '已关闭自动委派。已经开始的调用不受影响。')
        except OSError:
            status.text = '无法保存自动委派设置。'

    def restore_deleted():
        import sqlite3
        from .chat_sync import queue_restore

        if not (view.lan_sync_event or (view.lan_host and view.lan_host.sync_enabled)):
            status.text = '请先在两端开启双向聊天同步。'
            return

        def confirm():
            try:
                with view.history.db:
                    count = queue_restore(view.history.db)
                status.text = (f'已请求找回 {count} 条对话；稍后到历史列表查看。' if count
                               else '本机没有可向另一端查询的删除记录。')
            except sqlite3.Error:
                status.text = '暂时无法排队，请稍后重试。'

        view.action_sheet('找回本机已删对话', [('从另一端找回仍保留的对话', confirm)])

    if mobile:
        entry = field(hint_text='粘贴完整配对串', size_hint_y=None, height=dp(64))
        body.add_widget(entry)
        peer = root / 'lan-computer.json'
        pending = False

        def sync_toggle():
            if view.lan_sync_event is not None:
                view.stop_lan_sync()
                sync_button.text = '开启双向聊天同步'
                status.text = '已停止同步'
                try:
                    clear_auto_sync()
                except OSError:
                    status.text = '同步已停止，但未能关闭启动时自动同步。'
            elif peer.exists():
                view.start_lan_sync()
                sync_button.text = '停止双向聊天同步'
                status.text = '正在同步；可关闭此窗口继续聊天。'
            else:
                status.text = '请先配对电脑'

        def scan():
            if pending or peer.exists():
                status.text = '已有配对电脑，换电脑请先解除旧配对。' if peer.exists() else '正在连接电脑…'
                return

            def scanned(photo):
                from .pairing_qr import decode_android
                try:
                    code = decode_android(photo)
                except Exception:
                    Clock.schedule_once(lambda _: setattr(status, 'text', '未识别到 TalkApp 配对码，请重拍或粘贴配对串。'))
                    return

                def accept(_):
                    if popup.parent and not pending:
                        entry.text = code
                        status.text = '已识别配对码，请点「配对电脑」确认。'
                Clock.schedule_once(accept)

            view.android.take_photo(scanned)

        def run(connect):
            nonlocal pending
            if pending:
                return
            if connect and peer.exists():
                status.text = '请先在两端解除旧配对，再配对新电脑。'
                return
            code = entry.text
            pending = True
            close.disabled = forget_button.disabled = True
            status.text = '正在连接电脑…'

            def worker():
                try:
                    if connect:
                        lan_pairing.pair(root, code)
                    else:
                        lan_pairing.check(root)
                    message = '配对成功 · 加密连接正常' if connect else '加密连接正常'
                except (OSError, ValueError) as exc:
                    message = str(exc) if isinstance(exc, ValueError) else '无法连接电脑。请检查局域网、电脑防火墙和配对窗口。'

                def done(_):
                    nonlocal pending
                    pending = False
                    close.disabled = forget_button.disabled = False
                    status.text = message
                    if connect and peer.exists():
                        entry.text = ''
                Clock.schedule_once(done)
            threading.Thread(target=worker, daemon=True).start()

        def forget():
            try:
                view.stop_lan_sync()
                sync_button.text = '开启双向聊天同步'
                peer.unlink(missing_ok=True)
                lan_opencode.set_enabled(root, False)
                delegate_button.text = delegate_caption()
                with view.history.db:
                    view.history.db.execute("UPDATE lan_opencode SET state='done' WHERE state='outgoing'")
                clear_auto_sync()
                status.text = '已在手机移除绑定；也请在电脑解除配对。'
            except OSError:
                status.text = '无法移除配对记录'

        action('拍摄配对二维码', scan)
        action('配对电脑', lambda: run(True))
        action('测试连接', lambda: run(False))
        forget_button = action('移除本机绑定', forget)
        sync_button = action('停止双向聊天同步' if view.lan_sync_event else '开启双向聊天同步', sync_toggle)
        status.text = '已有配对电脑' if peer.exists() else '尚未配对'
    else:
        peer = root / 'lan-phone.json'
        host_address = view.lan_host.address if view.lan_host else lan_pairing.auto_sync(root, False)
        address = field(host_address or lan_pairing.local_address(), hint_text='电脑 Wi-Fi 的 IPv4 地址', multiline=False,
                        size_hint_y=None, height=dp(42))
        entry = field(hint_text='一次性配对串', readonly=True, size_hint_y=None, height=dp(64))
        body.add_widget(address)
        body.add_widget(entry)
        waiting = False
        qr_popup = None

        def start():
            nonlocal waiting
            try:
                ip = lan_pairing.lan_address(address.text.strip())
                host = view.start_lan_host(ip)
                if host.paired():
                    status.text = '手机已配对，可在手机点「测试连接」。'
                else:
                    entry.text = host.invitation()
                    waiting = True
                    status.text = '等待手机配对 · 配对串有效期 5 分钟'
            except (OSError, ValueError):
                status.text = '无法监听。请填写电脑实际局域网 IPv4，并检查端口是否被占用。'

        def show_qr():
            nonlocal qr_popup
            if not entry.text:
                start()
            if not entry.text:
                return
            try:
                from .pairing_qr import image_bytes
                texture = CoreImage(BytesIO(image_bytes(entry.text)), ext='png').texture
            except (ImportError, OSError, ValueError):
                status.text = '无法显示二维码，可以复制配对串。'
                return
            qr_body = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(8))
            qr_body.add_widget(Image(texture=texture, allow_stretch=True, keep_ratio=True))
            qr_popup = Popup(title='请在手机 TalkApp 中拍摄此二维码', content=qr_body,
                             size_hint=(.85, .85), auto_dismiss=False)
            qr_body.add_widget(button('关闭二维码', qr_popup.dismiss, size_hint_y=None, height=dp(42)))
            qr_popup.open()

        def forget():
            nonlocal waiting
            try:
                if view.lan_host:
                    view.lan_host.forget()
                    view.stop_lan_sync()
                else:
                    peer.unlink(missing_ok=True)
                lan_opencode.set_enabled(root, False)
                delegate_button.text = delegate_caption()
                with view.history.db:
                    view.history.db.execute("UPDATE lan_opencode SET state='done' WHERE state IN ('pending','running')")
                clear_auto_sync()
                waiting = False
                entry.text = ''
                status.text = '已解除手机的授权；也请在手机移除本机绑定。'
            except OSError:
                status.text = '无法移除配对记录'

        def refresh(_):
            nonlocal waiting
            if waiting and view.lan_host:
                paired = view.lan_host.paired()
                if paired or not view.lan_host.invitation_active():
                    waiting = False
                    entry.text = ''
                    if qr_popup:
                        qr_popup.dismiss()
                    status.text = '手机配对成功 · 可在手机测试连接' if paired else '配对码已过期，请重新生成。'

        def leave(*_):
            timer.cancel()
            if view.lan_host and not view.lan_host.sync_enabled:
                view.stop_lan_sync()

        def sync_toggle():
            if view.lan_host and view.lan_host.sync_enabled:
                view.stop_lan_sync()
                sync_button.text = '开启双向聊天同步'
                status.text = '已停止同步'
                try:
                    clear_auto_sync()
                except OSError:
                    status.text = '同步已停止，但未能关闭启动时自动同步。'
                return
            if not peer.exists():
                status.text = '请先配对手机'
                return
            try:
                view.enable_lan_host(address.text.strip())
                sync_button.text = '停止双向聊天同步'
                status.text = '同步已开启；可关闭此窗口继续聊天。'
            except (OSError, ValueError):
                status.text = '无法开启同步，请检查电脑局域网 IPv4 和防火墙。'

        action('生成配对串 / 开启监听', start)
        action('显示配对二维码', show_qr)
        action('复制配对串', lambda: Clipboard.copy(entry.text) if entry.text else None)
        action('解除手机配对', forget)
        sync_button = action('停止双向聊天同步' if view.lan_host and view.lan_host.sync_enabled else '开启双向聊天同步', sync_toggle)
        status.text = '已有配对手机，可开启监听后测试' if peer.exists() else '尚未配对'
        timer = Clock.schedule_interval(refresh, .5)
        popup.bind(on_dismiss=leave)

    def toggle_auto_sync():
        try:
            if lan_pairing.auto_sync(root, mobile):
                clear_auto_sync()
                status.text = '已关闭自动同步；本次同步状态不变。'
            elif not peer.is_file():
                status.text = '请先完成设备配对。'
            else:
                lan_pairing.set_auto_sync(root, True if mobile else address.text.strip())
                auto_button.text = auto_caption()
                status.text = '下次打开 TalkApp 时自动同步。若要现在开始，请点「开启双向聊天同步」。'
        except (OSError, ValueError):
            status.text = '无法保存自动同步设置，请检查配对和局域网地址。'

    auto_button = action(auto_caption(), toggle_auto_sync)
    delegate_button = action(delegate_caption(), toggle_delegate)
    action('找回本机已删对话', restore_deleted)
    close = action('关闭', popup.dismiss)
    popup.open()
