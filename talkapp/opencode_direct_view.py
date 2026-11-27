"""Mobile entry for checking a direct OpenCode connection and reading sessions."""
import threading

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from .opencode_direct import DirectClient
from .storage import data_dir


def open_direct(view):
    from .ui import button, field, label

    address_path = data_dir() / 'opencode-direct-address.txt'
    try:
        previous = address_path.read_text(encoding='utf-8')
    except OSError:
        previous = ''
    body = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(6))
    popup = Popup(title='直连 OpenCode · 只读', content=body, size_hint=(.94, .72))
    body.add_widget(label('使用电脑后台的私有 HTTPS 地址。不需要桌面 TalkApp 或无线调试。密码不保存到磁盘。',
                          size_hint_y=None, height=dp(82)))
    address = field(previous, hint_text='https://电脑名.…ts.net', multiline=False, size_hint_y=None, height=dp(44))
    password = field(hint_text='OpenCode 服务密码', password=True, multiline=False, size_hint_y=None, height=dp(44))
    status = label('')
    for item in (address, password, status):
        body.add_widget(item)

    def run(work, done):
        if connect.disabled:
            return
        connect.disabled = True
        status.text = '正在连接…'

        def worker():
            result, error = None, ''
            try:
                result = work()
            except ValueError as exc:
                error = str(exc)
            except Exception:
                error = '无法读取 OpenCode 数据'

            def finish(_):
                connect.disabled = False
                if not popup.parent or view.closed:
                    return
                if error:
                    status.text = error
                else:
                    done(result)

            Clock.schedule_once(finish)

        threading.Thread(target=worker, daemon=True).start()

    def load_sessions():
        try:
            client = DirectClient(address.text, password.text)
        except ValueError as exc:
            status.text = str(exc)
            return

        def show_messages(title, text):
            status.text = '已连接 · 只读'
            panel = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(8))
            # Keep server text read-only and transient; do not import it into TalkApp history.
            panel.add_widget(field(text or '没有可显示的文字消息', readonly=True))
            dialog = Popup(title=title, content=panel, size_hint=(.95, .85))
            panel.add_widget(button('关闭', dialog.dismiss, size_hint_y=None, height=dp(40)))
            dialog.open()

        def choose(rows):
            try:
                address_path.write_text(client.address, encoding='utf-8')
            except OSError:
                pass
            status.text = '已连接 · 只读' if rows else '已连接，暂无会话'
            if rows:
                view.action_sheet('OpenCode 会话', [
                    (title, lambda sid=sid, title=title: run(lambda: client.messages(sid),
                                                             lambda text: show_messages(title, text)))
                    for sid, title in rows])

        run(client.sessions, choose)

    connect = button('连接并查看会话', load_sessions, size_hint_y=None, height=dp(44))
    body.add_widget(connect)
    body.add_widget(button('关闭', popup.dismiss, size_hint_y=None, height=dp(38)))
    popup.bind(on_dismiss=lambda *_: setattr(password, 'text', ''))
    popup.open()
