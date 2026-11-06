"""AI 设置弹窗：输入 API key / base url / model / system prompt，保存 + 测试连接。"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle, Line
from config import theme
from talkapp.storage import Config as LLMConfig
import llm_client
import sounds
from utils.appearance import state as appearance
from kivy.clock import Clock
from kivy.utils import escape_markup

# 供应商预设：name -> {"base":..., "models":[...]}；None 表示自定义
# OpenCode 是聚合端点，已包含 minimax/kimi/glm/deepseek/qwen/mimo 全家
_OPENCODE_BASE = "https://opencode.ai/zen/go"
PROVIDERS = {
    "DeepSeek": {"base": "https://api.deepseek.com",
                 "models": ["deepseek-v4-flash", "deepseek-v4-pro"]},
    "OpenCode": {"base": _OPENCODE_BASE, "models": [
        "mimo-v2-omni", "mimo-v2-pro", "mimo-v2.5-pro", "mimo-v2.5",
        "glm-5.2", "glm-5.1", "glm-5",
        "deepseek-v4-pro", "deepseek-v4-flash",
        "kimi-k2.7-code", "kimi-k2.6", "kimi-k2.5",
        "qwen3.7-max", "qwen3.7-plus", "qwen3.6-plus", "qwen3.5-plus",
        "minimax-m3", "minimax-m2.7", "minimax-m2.5",
        "hy3-preview",
    ]},
    "MiMo": {"base": _OPENCODE_BASE, "models": [
        "mimo-v2-omni", "mimo-v2-pro", "mimo-v2.5-pro", "mimo-v2.5",
    ]},
    "MiMo直连": {"base": "https://api.xiaomimimo.com/v1",
                 "models": ["mimo-v2.5-pro", "mimo-v2.5"],
                 "labels": {"mimo-v2.5-pro": "mimo-v2.5-pro [仅文本]",
                            "mimo-v2.5": "mimo-v2.5 [图/音/视]"}},
    "OpenAI": {"base": "https://api.openai.com/v1",
               "models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o"]},
    "通义千问": {"base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                 "models": ["qwen-plus", "qwen-turbo", "qwen-max"]},
    "Moonshot": {"base": "https://api.moonshot.cn/v1",
                 "models": ["moonshot-v1-8k", "moonshot-v1-32k"]},
    "硅基流动": {"base": "https://api.siliconflow.cn/v1", "models": []},
    "Ollama": {"base": "http://127.0.0.1:11434/v1", "models": []},
    "自定义": None,
}


class AISettingsPopup(ModalView):
    def __init__(self, **kwargs):
        super().__init__(size_hint=(0.92, 0.9), **kwargs)
        self.background = ""
        self.background_color = (0, 0, 0, 0)
        self._cfg = LLMConfig.load()
        self._provider_drafts = {}
        self._active_provider = '自定义'
        self._model_request = 0
        self._test_request = 0
        self._build_ui()

    def _build_ui(self):
        root = BoxLayout(orientation="vertical")
        with root.canvas.before:
            Color(*theme.CHASSIS)
            self._bg = Rectangle(pos=root.pos, size=root.size)
            Color(*theme.METAL_LIGHT)
            self._line = Line(rectangle=(*root.pos, *root.size), width=dp(1))
        root.bind(
            pos=lambda _, p: (setattr(self._bg, "pos", p),
                               setattr(self._line, "rectangle",
                                       (p[0], p[1], root.width, root.height))),
            size=lambda _, s: (setattr(self._bg, "size", s),
                               setattr(self._line, "rectangle",
                                       (root.x, root.y, s[0], s[1]))),
        )
        root.padding = [dp(14), dp(12)]
        root.spacing = dp(8)

        hdr = BoxLayout(size_hint_y=None, height=dp(38))
        hdr.add_widget(Label(text="[b]SYSTEM CONFIG[/b]\nAI 与外观设置", markup=True,
                             color=theme.VFD_CYAN, font_size=dp(13),
                              halign="left", valign="middle"))
        close = Button(text="[font=Symbols]✕[/font]", markup=True,
                       size_hint_x=None, width=dp(36),
                       background_normal="", background_color=(0, 0, 0, 0),
                       color=theme.TEXT_MUTED, font_size=dp(18))
        close.bind(on_release=lambda _: self.dismiss())
        hdr.add_widget(close)
        root.add_widget(hdr)

        theme_title = Label(text='APPEARANCE / 界面主题（立即生效）',
                            color=theme.TEXT_SECONDARY, font_size=dp(12),
                            size_hint_y=None, height=dp(20))
        root.add_widget(theme_title)
        theme_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        self._theme_buttons = {}
        for name, caption in (('classic', '经典黑钛 · 上一版'),
                              ('enhanced', '增强黑钛 · 新版')):
            button = Button(text=caption, font_size=dp(12), background_normal='')
            button.bind(on_release=lambda _, value=name: self._select_theme(value))
            self._theme_buttons[name] = button
            theme_row.add_widget(button)
        root.add_widget(theme_row)
        self._refresh_theme_buttons()

        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        form = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(12))
        form.bind(minimum_height=form.setter("height"))
        preset_row = GridLayout(cols=3, size_hint_y=None,
                                height=dp(38 * ((len(PROVIDERS) + 2) // 3)), spacing=dp(5))
        self._provider_buttons = {}
        for name in PROVIDERS:
            b = Button(text=name, markup=True, font_size=dp(theme.FONT_LABEL),
                       background_normal="", background_color=theme.PANEL_RAISED,
                       color=theme.TEXT_SECONDARY)
            b.bind(on_release=lambda _, n=name: self._apply_preset(n))
            self._provider_buttons[name] = b
            preset_row.add_widget(b)
        form.add_widget(preset_row)

        self._key = self._field("API Key", self._cfg.api_key, password=True, hint="sk-...")
        self._base = self._field("Base URL", self._cfg.api_base_url, hint="https://api.deepseek.com")
        self._model_box, self._model_btns, self._selected_model = self._build_model_box()
        self._model_input = TextInput(text=self._cfg.model, multiline=False,
            font_size=dp(13), size_hint_y=None, height=dp(40),
            background_normal='', background_active='',
            background_color=theme.DISPLAY_GLASS, foreground_color=theme.TEXT_PRIMARY,
            cursor_color=theme.VFD_CYAN, padding=[dp(8), dp(8)],
            hint_text='模型 ID（可直接输入任意兼容模型）', hint_text_color=theme.TEXT_MUTED)
        self._model_input.bind(text=self._on_model_text)
        form.add_widget(self._key)
        form.add_widget(self._base)
        form.add_widget(self._model_input)
        self._fetch_btn = Button(text='读取服务商模型列表', size_hint_y=None, height=dp(36),
            background_normal='', background_color=theme.METAL_DARK,
            color=theme.VFD_BLUE, font_size=dp(12))
        self._fetch_btn.bind(on_release=lambda _: self._fetch_models())
        form.add_widget(self._fetch_btn)
        form.add_widget(self._model_box)
        self._sys = self._field("System Prompt", self._cfg.system_prompt,
                                multiline=True, height=dp(90),
                                hint="你是一个健身助手...")
        form.add_widget(self._sys)
        scroll.add_widget(form)
        root.add_widget(scroll)
        self._init_model_for_current()

        self._status = Label(text="", color=theme.TEXT_MUTED, font_size=dp(11),
                             halign="left", valign="middle", size_hint_y=None,
                             height=dp(36), markup=True)
        self._status.bind(size=self._status.setter("text_size"))
        root.add_widget(self._status)

        btn_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        test_btn = Button(text="测试连接", background_normal="",
                           background_color=theme.METAL_DARK,
                           color=theme.TEXT_PRIMARY, font_size=dp(14))
        test_btn.bind(on_release=lambda _: self._test())
        btn_row.add_widget(test_btn)
        save_btn = Button(text="保存", background_normal="",
                           background_color=theme.VFD_CYAN,
                           color=(0.05, 0.05, 0.08, 1), font_size=dp(14))
        save_btn.bind(on_release=lambda _: self._save())
        btn_row.add_widget(save_btn)
        root.add_widget(btn_row)

        self.add_widget(root)
        sounds.bind_feedback(root)

    def _refresh_theme_buttons(self):
        selected = 'enhanced' if appearance.enhanced else 'classic'
        for name, button in self._theme_buttons.items():
            active = name == selected
            button.background_color = theme.VFD_CYAN if active else theme.PANEL_RAISED
            button.color = theme.CHASSIS if active else theme.TEXT_SECONDARY

    def _select_theme(self, name):
        try:
            appearance.select(name)
        except OSError:
            self._status.text = '主题保存失败，请检查存储空间'
            return
        self._refresh_theme_buttons()
        self._status.text = '主题已切换并保存，下次启动自动恢复'

    def _field(self, title, value, password=False, multiline=False, height=dp(48), hint=""):
        box = BoxLayout(orientation="vertical", size_hint_y=None,
                        height=height + dp(16), spacing=dp(2))
        lbl = Label(text=title.upper(), color=theme.METAL_LIGHT, font_size=dp(theme.FONT_LABEL),
                    halign="left", valign="middle", size_hint_y=None, height=dp(14))
        lbl.bind(size=lbl.setter("text_size"))
        box.add_widget(lbl)
        ti = TextInput(text=value, multiline=multiline, password=password,
                       font_size=dp(13), foreground_color=theme.TEXT_PRIMARY,
                       background_normal="", background_color=theme.DISPLAY_GLASS,
                       cursor_color=theme.VFD_CYAN, padding=[dp(8), dp(4)],
                       hint_text=hint, hint_text_color=theme.TEXT_MUTED)
        box.add_widget(ti)
        return box

    def _build_model_box(self):
        box = BoxLayout(orientation="vertical", size_hint_y=None,
                        spacing=dp(2))
        box.bind(minimum_height=box.setter("height"))
        lbl = Label(text="MODEL SELECT", color=theme.METAL_LIGHT, font_size=dp(theme.FONT_LABEL),
                    halign="left", valign="middle", size_hint_y=None, height=dp(14))
        lbl.bind(size=lbl.setter("text_size"))
        box.add_widget(lbl)
        self._model_grid = GridLayout(cols=2, size_hint_y=None,
                                      spacing=dp(5))
        self._model_grid.bind(minimum_height=self._model_grid.setter("height"))
        box.add_widget(self._model_grid)
        return box, {}, self._cfg.model

    def _init_model_for_current(self):
        base = self._cfg.api_base_url.rstrip("/")
        prov = "自定义"
        for name, info in PROVIDERS.items():
            if info and info["base"].rstrip("/") == base:
                prov = name
                break
        self._render_models(prov)
        self._active_provider = prov
        self._refresh_provider_buttons()

    def _render_models(self, provider_name):
        self._model_grid.clear_widgets()
        self._model_btns = {}
        info = PROVIDERS.get(provider_name)
        models = info['models'] if info else []
        self._populate_models(models, info.get('labels', {}) if info else {})

    def _populate_models(self, models, labels=None):
        self._model_grid.clear_widgets()
        self._model_btns = {}
        labels = labels or {}
        if not models:
            tip = Label(text="直接填写模型 ID，或读取服务商列表",
                        color=theme.TEXT_MUTED, font_size=dp(11),
                        halign="left", valign="middle",
                        size_hint_y=None, height=dp(20))
            tip.bind(size=tip.setter("text_size"))
            self._model_grid.add_widget(tip)
            return
        for m in models:
            label = labels.get(m, m)
            b = Button(text=label, font_size=dp(theme.FONT_LABEL),
                       size_hint_y=None, height=dp(38), shorten=True, shorten_from='right',
                       background_normal="", background_color=theme.PANEL_RAISED,
                       color=theme.TEXT_SECONDARY)
            b.bind(on_release=lambda _, mm=m: self._select_model(mm))
            self._model_btns[m] = b
            b.bind(size=lambda widget, size: setattr(widget, 'text_size',
                                                     (max(0, size[0] - dp(12)), size[1])))
            self._model_grid.add_widget(b)
        self._on_model_text(self._model_input, self._model_input.text)

    def _select_model(self, m):
        self._model_input.text = m
        self._on_model_text(self._model_input, m)

    def _on_model_text(self, _input, m):
        m = m.strip()
        self._selected_model = m
        for mm, b in self._model_btns.items():
            if mm == m:
                b.background_color = theme.VFD_CYAN
                b.color = (0.05, 0.05, 0.08, 1)
            else:
                b.background_color = theme.PANEL_RAISED
                b.color = theme.TEXT_SECONDARY

    def _read(self):
        self._cfg.api_key = self._key.children[0].text.strip()
        self._cfg.api_base_url = self._base.children[0].text.strip()
        self._cfg.model = (self._selected_model or "").strip()
        self._cfg.system_prompt = self._sys.children[0].text.strip()

    def _apply_preset(self, name):
        if name == self._active_provider:
            return
        self._provider_drafts[self._active_provider] = (
            self._key.children[0].text, self._base.children[0].text, self._model_input.text)
        info = PROVIDERS.get(name)
        self._active_provider = name
        self._model_request += 1
        self._fetch_btn.disabled = False
        self._fetch_btn.text = '读取服务商模型列表'
        draft = self._provider_drafts.get(name)
        if draft:
            key, base, model = draft
        elif info:
            stored = next((item for item in LLMConfig.profiles() if item['api_base_url'].rstrip('/') == info['base'].rstrip('/')), None)
            key, base, model = ((stored['api_key'], stored['api_base_url'], stored['model']) if stored else
                                ('', info['base'], next(iter(info['models']), '')))
        else:
            key, base, model = '', '', ''
        self._key.children[0].text = key
        self._base.children[0].text = base
        self._model_input.text = model
        self._render_models(name)
        self._refresh_provider_buttons()
        self._status.text = f'已选择 {name}，模型可手填；保存后生效'

    def _refresh_provider_buttons(self):
        for name, button in self._provider_buttons.items():
            active = name == self._active_provider
            button.background_color = theme.VFD_BLUE if active else theme.PANEL_RAISED
            button.color = theme.CHASSIS if active else theme.TEXT_SECONDARY

    def _fetch_models(self):
        import threading
        import httpx
        base = self._base.children[0].text.strip().rstrip('/')
        key = self._key.children[0].text.strip()
        if not base.startswith(('https://', 'http://')):
            self._status.text = '请先填写有效的 Base URL'
            return
        self._model_request += 1
        request_id = self._model_request
        self._fetch_btn.disabled = True
        self._fetch_btn.text = '读取中…'
        from urllib.parse import urlparse
        prefix = base.removesuffix('/chat/completions')
        url = prefix + ('/v1/models' if not urlparse(prefix).path else '/models')

        def finish(models, error):
            if request_id != self._model_request:
                return
            self._fetch_btn.disabled = False
            self._fetch_btn.text = '读取服务商模型列表'
            if error:
                self._status.text = error
            else:
                self._populate_models(models)
                self._status.text = f'已读取 {len(models)} 个模型；也可继续手填'

        def worker():
            try:
                with httpx.Client(timeout=20, follow_redirects=False) as client:
                    response = client.get(url, headers=llm_client._build_headers(key, base))
                    response.raise_for_status()
                    rows = response.json().get('data', [])
                models = sorted({row['id'] for row in rows
                    if isinstance(row, dict) and isinstance(row.get('id'), str)})[:200]
                Clock.schedule_once(lambda dt: finish(models, None))
            except Exception:
                Clock.schedule_once(lambda dt: finish([], '无法读取模型列表，请检查地址和 Key，或手填模型 ID'))
        threading.Thread(target=worker, daemon=True).start()

    def _save(self):
        self._read()
        try:
            self._cfg.save()
        except (ValueError, OSError) as exc:
            self._set_status(False, str(exc))
            return
        self._status.text = "[color=88ccff]已保存[/color]"
        self._status.color = theme.TEXT_PRIMARY

    def _test(self):
        self._read()
        if not self._cfg.is_configured:
            self._status.text = "[color=ff4444]请先填写 key / base / model[/color]"
            return
        self._status.text = "连接中..."
        self._test_request += 1
        request_id = self._test_request
        config = (self._cfg.api_key, self._cfg.api_base_url, self._cfg.model)
        import threading
        from kivy.clock import Clock

        def worker():
            try:
                c = llm_client.LLMClient(
                    api_key=config[0], api_base_url=config[1],
                    model=config[2], temperature=0.3, max_tokens=16,
                    max_retries=1, timeout=30.0,
                )
                try:
                    txt = c.chat_text([{"role": "user", "content": "回复 ok"}])
                finally:
                    c.close()
                msg_ok = txt[:30]
                Clock.schedule_once(
                    lambda dt: self._set_status(True, msg_ok) if request_id == self._test_request else None, 0)
            except Exception as e:
                msg_err = str(e)[:120]

                Clock.schedule_once(
                    lambda dt: self._set_status(False, msg_err) if request_id == self._test_request else None, 0)

        threading.Thread(target=worker, daemon=True).start()

    def _set_status(self, ok, msg):
        msg = escape_markup(msg)
        if ok:
            self._status.text = f"[color=88ffaa]连接成功：{msg}[/color]"
        else:
            self._status.text = f"[color=ff4444]失败：{msg}[/color]"
