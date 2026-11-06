"""Respect Android edge-to-edge status bars, cutouts and gesture navigation."""
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import platform


class SafeArea:
    def __init__(self, layout):
        self.layout = layout
        self.closed = False
        self.event = None
        if platform == 'android':
            self.event = Clock.schedule_interval(self.refresh, .5)
            self.refresh()

    def refresh(self, *_):
        if self.closed:
            return
        from android.runnable import run_on_ui_thread
        @run_on_ui_thread
        def read():
            from jnius import autoclass
            activity = autoclass('org.kivy.android.PythonActivity').mActivity
            decor = activity.getWindow().getDecorView()
            insets = decor.getRootWindowInsets()
            if insets is None:
                return
            version = autoclass('android.os.Build$VERSION').SDK_INT
            if version >= 30:
                types = autoclass('android.view.WindowInsets$Type')
                bars = insets.getInsetsIgnoringVisibility(types.statusBars() | types.navigationBars() | types.displayCutout())
                values = (bars.left, bars.top, bars.right, bars.bottom)
            else:
                values = (insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                          insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom())
            width = max(1, decor.getWidth())
            Clock.schedule_once(lambda _: self.apply(values, width))
        read()

    def apply(self, values, native_width):
        if self.closed:
            return
        ratio = Window.width / native_width
        padding = [round(value * ratio) for value in values]
        if list(self.layout.padding) != padding:
            self.layout.padding = padding

    def close(self):
        self.closed = True
        if self.event:
            self.event.cancel()
