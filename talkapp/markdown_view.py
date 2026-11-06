"""Lightweight mobile Markdown blocks: text, lists, tables, fenced code and links."""
import re
import webbrowser

from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.textinput import TextInput
from kivy.uix.codeinput import CodeInput
from kivy.utils import escape_markup

from . import theme
from utils.appearance import state as appearance


def inline(text):
    text = escape_markup(text)
    # Preserve escaped user markup: only our generated tags are interpreted.
    text = re.sub(r'\*\*(.+?)\*\*', r'[b]\1[/b]', text)
    text = re.sub(r'`([^`]+)`', r'[color=33ccff]\1[/color]', text)
    text = re.sub(r'&bl;([^\n]+?)&br;\((https?://[^\s)]+)\)', r'[ref=\2][color=33ccff]\1[/color][/ref]', text)
    return text


def blocks(text):
    result = []
    # Fences need stateful handling; unmatched fence is still displayed as code.
    kind, buffer, language = 'text', [], ''
    for line in text.splitlines():
        if line.startswith('```'):
            if kind == 'text':
                if buffer:
                    result.append(('text', '\n'.join(buffer), ''))
                kind, buffer, language = 'code', [], line[3:].strip()
            else:
                result.append(('code', '\n'.join(buffer), language))
                kind, buffer, language = 'text', [], ''
        else:
            buffer.append(line)
    if buffer:
        result.append((kind, '\n'.join(buffer), language))
    return result


class MarkdownView(BoxLayout):
    def __init__(self, text='', **kwargs):
        super().__init__(orientation='vertical', size_hint_y=None, spacing=dp(6), **kwargs)
        self.bind(minimum_height=self.setter('height'))
        for kind, value, language in blocks(text):
            if kind == 'code':
                header = Button(text=(language or '代码') + ' / 复制代码', size_hint_y=None, height=dp(28),
                                font_size=dp(11), background_normal='', background_color=theme.METAL_DARK,
                                color=theme.VFD_CYAN)
                header.bind(on_release=lambda _, code=value: Clipboard.copy(code))
                self.add_widget(header)
                self.add_raw(value, language)
            else:
                self.add_text(value)

    def add_raw(self, text, language=''):
        from pygments.lexers import get_lexer_by_name, TextLexer
        from pygments.util import ClassNotFound
        try:
            lexer = get_lexer_by_name(language or 'text')
        except ClassNotFound:
            lexer = TextLexer()
        view = CodeInput(text=text, lexer=lexer, style_name='monokai', readonly=True, size_hint_y=None, font_size=dp(14) * appearance.font_scale,
                         background_normal='', background_active='', background_color=theme.DISPLAY_GLASS,
                         foreground_color=theme.TEXT_PRIMARY, padding=[dp(8), dp(6)])
        def resize(*_):
            view.height = max(dp(32), len(view._lines) * view.line_height + dp(14))
        view.bind(width=resize, text=resize)
        from kivy.clock import Clock
        Clock.schedule_once(lambda _: resize())
        self.add_widget(view)

    def add_text(self, text):
        lines = text.splitlines()
        table_start = next((i for i in range(len(lines) - 1) if '|' in lines[i] and
                            re.match(r'^\s*\|?\s*:?-{3,}', lines[i + 1])), None)
        if table_start is not None:
            end = table_start + 2
            while end < len(lines) and '|' in lines[end] and lines[end].strip():
                end += 1
            if table_start:
                self.add_text('\n'.join(lines[:table_start]))
            rows = [line.strip().strip('|').split('|') for line in
                    [lines[table_start]] + lines[table_start + 2:end]]
            columns = len(rows[0])
            grid = GridLayout(cols=columns, size_hint_y=None, spacing=dp(3))
            grid.bind(minimum_height=grid.setter('height'))
            for index, row in enumerate(rows):
                for cell in (row + [''] * columns)[:columns]:
                    value = Label(text=inline(cell.strip()), markup=True, bold=index == 0,
                                  size_hint_y=None, halign='left', valign='top', font_size=dp(14) * appearance.font_scale,
                                  color=theme.VFD_CYAN if index == 0 else theme.TEXT_PRIMARY)
                    value.bind(width=lambda w, size: setattr(w, 'text_size', (size, None)),
                               texture_size=lambda w, size: setattr(w, 'height', size[1] + dp(10)))
                    grid.add_widget(value)
            self.add_widget(grid)
            if end < len(lines):
                self.add_text('\n'.join(lines[end:]))
            return
        rendered = []
        for line in text.splitlines():
            if re.match(r'^\s*\|?\s*:?-{3,}', line):
                continue
            heading = re.match(r'^(#{1,6})\s+(.+)', line)
            if heading:
                size = 21 if len(heading[1]) == 1 else 17
                rendered.append(f'[size={int(dp(size) * appearance.font_scale)}][b]{inline(heading[2])}[/b][/size]')
            elif line.startswith('> '):
                rendered.append('[color=aaaaaa]│ ' + inline(line[2:]) + '[/color]')
            elif re.match(r'^\s*[-*+]\s+', line):
                rendered.append('• ' + inline(re.sub(r'^\s*[-*+]\s+', '', line)))
            else:
                rendered.append(inline(line))
        # Tables retain rows/columns as wrapped text; wide cells remain readable on phones.
        view = Label(text='\n'.join(rendered), markup=True, size_hint_y=None, halign='left', valign='top',
                     color=theme.TEXT_PRIMARY, font_size=dp(15) * appearance.font_scale)
        view.bind(width=lambda w, width: setattr(w, 'text_size', (max(dp(20), width), None)),
                  texture_size=lambda w, size: setattr(w, 'height', size[1] + dp(8)))
        view.bind(on_ref_press=lambda _, url: webbrowser.open(url) if url.startswith(('https://', 'http://')) else None)
        self.add_widget(view)
