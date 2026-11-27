"""Single-line text that scrolls only when it cannot fit."""
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import ColorProperty, NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.label import Label
from kivy.uix.stencilview import StencilView


class MarqueeLabel(StencilView):
    text = StringProperty('')
    color = ColorProperty((1, 1, 1, 1))
    font_size = NumericProperty('11sp')
    inset = NumericProperty(0)
    offset = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.caption = Label(size_hint=(None, None))
        self.add_widget(self.caption)
        self.restart = Clock.create_trigger(self._restart)
        self.bind(text=self._sync, color=self._sync, font_size=self._sync,
                  width=self.restart, inset=self.restart, parent=self.restart,
                  pos=self._place, height=self._place, offset=self._place)
        self.caption.bind(texture_size=self.restart)
        self._sync()
        self.restart()

    def _sync(self, *_):
        self.caption.text = ' '.join(self.text.splitlines())
        self.caption.color = self.color
        self.caption.font_size = self.font_size

    def _place(self, *_):
        self.caption.pos = (self.x + self.inset - self.offset, self.y)
        self.caption.size = (self.caption.texture_size[0], self.height)

    @property
    def overflow(self):
        return max(0, self.caption.texture_size[0] - max(0, self.width - 2 * self.inset))

    def _restart(self, *_):
        Animation.cancel_all(self, 'offset')
        self.offset = 0
        self._place()
        distance = self.overflow
        if not self.parent or self.width <= 2 * self.inset or distance < 1:
            return
        duration = distance / dp(33)
        motion = (Animation(offset=0, duration=1.0) + Animation(offset=distance, duration=duration)
                  + Animation(offset=distance, duration=1.1) + Animation(offset=0, duration=duration))
        motion.repeat = True
        motion.start(self)


class MarqueeButton(ButtonBehavior, MarqueeLabel):
    pass
