"""Persistent appearance preference, independent of AI credentials."""
import json
import os

from kivy.event import EventDispatcher
from kivy.properties import BooleanProperty, NumericProperty
from talkapp.storage import data_dir as _data_dir


class Appearance(EventDispatcher):
    enhanced = BooleanProperty(True)
    font_scale = NumericProperty(1.0)

    def __init__(self):
        super().__init__()
        try:
            with open(self.path, encoding='utf-8') as stream:
                value = json.load(stream)
                self.enhanced = value.get('theme', 'enhanced') != 'classic'
                self.font_scale = max(.85, min(1.6, float(value.get('font_scale', 1.0))))
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    @property
    def path(self):
        return os.path.join(_data_dir(), 'appearance.json')

    def select(self, name):
        if name not in ('classic', 'enhanced'):
            raise ValueError('Unknown theme')
        # Save first: a failed write must not silently pretend persistence succeeded.
        temporary = self.path + '.tmp'
        with open(temporary, 'w', encoding='utf-8') as stream:
            json.dump({'theme': name, 'font_scale': self.font_scale}, stream)
        os.replace(temporary, self.path)
        self.enhanced = name == 'enhanced'

    def set_font_scale(self, value):
        value = float(value)
        if value not in (.9, 1.0, 1.25, 1.5):
            raise ValueError('不支持的字号')
        temporary = self.path + '.tmp'
        with open(temporary, 'w', encoding='utf-8') as stream:
            json.dump({'theme': 'enhanced' if self.enhanced else 'classic', 'font_scale': value}, stream)
        os.replace(temporary, self.path)
        self.font_scale = value


state = Appearance()
