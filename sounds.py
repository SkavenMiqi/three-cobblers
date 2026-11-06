import os
import wave
import struct
import math
import random
import tempfile

from kivy.core.audio import SoundLoader
from kivy.utils import platform as _platform

_CACHE_DIR = None
_SOUNDS = {}
_ENABLED = True


def _writable_dir():
    global _CACHE_DIR
    if _CACHE_DIR:
        return _CACHE_DIR
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app and app.user_data_dir:
            _CACHE_DIR = app.user_data_dir
            os.makedirs(_CACHE_DIR, exist_ok=True)
            return _CACHE_DIR
    except Exception:
        pass
    _CACHE_DIR = tempfile.gettempdir()
    return _CACHE_DIR


def _write_wav(path, samples, rate=22050):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in samples)
        w.writeframes(frames)


def _gen_click(path):
    rate = 22050
    dur = 0.045
    n = int(rate * dur)
    samples = []
    for i in range(n):
        t = i / rate
        env = math.exp(-t * 85)
        metal = math.sin(2 * math.pi * 1450 * t)
        contact = 0.45 * math.sin(2 * math.pi * 410 * t)
        samples.append(0.48 * env * (metal + contact))
    _write_wav(path, samples, rate)


def _gen_explosion(path):
    rate = 22050
    dur = 0.45
    n = int(rate * dur)
    samples = []
    for i in range(n):
        t = i / rate
        env = math.exp(-t * 5)
        low = 0.5 * env * math.sin(2 * math.pi * 70 * t)
        noise = 0.3 * env * (random.uniform(-1, 1))
        rumble = 0.2 * env * math.sin(2 * math.pi * 45 * t)
        samples.append(low + noise + rumble)
    _write_wav(path, samples, rate)


def _gen_rest_complete(path):
    rate = 22050
    samples = []
    for frequency in (880, 1175):
        for i in range(int(rate * 0.16)):
            t = i / rate
            samples.append(0.35 * math.exp(-t * 8) * math.sin(2 * math.pi * frequency * t))
        samples.extend([0.0] * int(rate * 0.04))
    _write_wav(path, samples, rate)


def _ensure(name, gen_func):
    if name in _SOUNDS:
        return _SOUNDS[name]
    path = os.path.join(_writable_dir(), name + ".wav")
    if not os.path.exists(path):
        try:
            gen_func(path)
        except Exception:
            return None
    try:
        snd = SoundLoader.load(path)
        if snd:
            _SOUNDS[name] = snd
            return snd
    except Exception:
        pass
    return None


def _vibrate(seconds=0.3):
    if _platform != "android":
        return
    try:
        from android import mActivity
        ctx = mActivity
        v = ctx.getSystemService(ctx.VIBRATOR_SERVICE)
        if v and v.hasVibrator():
            v.vibrate(int(seconds * 1000))
    except Exception:
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            ctx = PythonActivity.mActivity
            Vibrator = autoclass("android.os.Vibrator")
            v = ctx.getSystemService("vibrator")
            if v and v.hasVibrator():
                v.vibrate(int(seconds * 1000))
        except Exception:
            pass


def play_click():
    if not _ENABLED:
        return
    snd = _ensure("click", _gen_click)
    if snd:
        try:
            snd.stop()
            snd.play()
        except Exception:
            pass


def play_explosion():
    if not _ENABLED:
        return
    snd = _ensure("explosion", _gen_explosion)
    if snd:
        try:
            snd.stop()
            snd.play()
        except Exception:
            pass
    _vibrate(0.3)


def play_rest_complete():
    if not _ENABLED:
        return
    snd = _ensure("rest_complete", _gen_rest_complete)
    if snd:
        try:
            snd.stop()
            snd.play()
        except Exception:
            pass
    _vibrate(0.2)


def lighten(color, factor=0.28):
    return tuple(min(1.0, c + (1.0 - c) * factor) if i < 3 else c for i, c in enumerate(color))


def bind_feedback(btn, bg_color=None, text_color=None):
    light_bg = lighten(bg_color) if bg_color else None
    light_text = lighten(text_color) if text_color else None

    def on_down(instance):
        play_click()
        if light_bg is not None:
            instance.background_color = light_bg
        if light_text is not None:
            instance.color = light_text

    def on_up(instance):
        if bg_color is not None:
            instance.background_color = bg_color
        if text_color is not None:
            instance.color = text_color

    btn.bind(on_press=on_down, on_release=on_up)
