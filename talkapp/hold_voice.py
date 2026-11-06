"""Fitness-style hold-to-record, release-to-send. No speech output or ASR."""
import base64
import io
import json
import threading
import time
import wave

from kivy.clock import Clock
from kivy.utils import platform
from .storage import data_dir


def audio_message(data, format):
    return json.dumps({'audio': {'data': base64.b64encode(data).decode('ascii'), 'format': format}})


class HoldVoice:
    def __init__(self, chat, button):
        self.chat, self.button = chat, button
        self.event = None
        self.stop = threading.Event()
        self.held = False
        self.recording = False
        self.recorder = None
        self.cancelled = False

    def press(self, *_):
        if self.chat.busy or self.recording:
            return
        self.held = True
        self.cancelled = False
        self.event = Clock.schedule_once(self.start, .3)

    def release(self, *_):
        self.held = False
        if self.event:
            self.event.cancel()
            self.event = None
        if not self.recording:
            return self.chat.notice('按住语音按钮说话，松开发送')
        self.stop.set()
        if platform == 'android':
            self.finish_android()

    def start(self, *_):
        self.event = None
        if not self.held or self.chat.busy:
            return
        if platform == 'android':
            from android.permissions import check_permission, request_permissions, Permission
            if not check_permission(Permission.RECORD_AUDIO):
                request_permissions([Permission.RECORD_AUDIO])
                return self.chat.notice('请授予录音权限后，再按住说话')
        self.recording = True
        self.stop = threading.Event()
        self.button.text = '[font=Symbols]●[/font]'
        self.button.background_color = (1, .2, .06, 1)
        self.chat.notice('正在录音 · 松开发送（最长60秒）')
        if platform == 'android':
            try:
                from jnius import autoclass
                self.path = data_dir() / 'hold-input.m4a'
                recorder = autoclass('android.media.MediaRecorder')()
                self.recorder = recorder
                recorder.setAudioSource(1)
                recorder.setOutputFormat(2)
                recorder.setAudioEncoder(3)
                recorder.setAudioSamplingRate(16000)
                recorder.setAudioEncodingBitRate(32000)
                recorder.setOutputFile(str(self.path))
                recorder.prepare()
                recorder.start()
                self.limit_event = Clock.schedule_once(lambda _: self.release(), 60)
            except Exception:
                self.cancel()
                self.chat.notice('启动录音失败，请检查权限和麦克风')
        else:
            threading.Thread(target=self.desktop, daemon=True).start()

    def desktop(self):
        try:
            import sounddevice as sd
            frames = []
            begin = time.monotonic()
            with sd.RawInputStream(samplerate=16000, channels=1, dtype='int16', blocksize=1600) as stream:
                while not self.stop.is_set() and time.monotonic() - begin < 60:
                    data, _ = stream.read(1600)
                    frames.append(bytes(data))
            if time.monotonic() - begin < .4:
                raise ValueError('录音太短，已取消')
            output = io.BytesIO()
            with wave.open(output, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b''.join(frames))
            Clock.schedule_once(lambda _: self.finish(output.getvalue(), 'wav'))
        except Exception as exc:
            message = str(exc) if isinstance(exc, ValueError) else '录音失败，请检查系统默认麦克风'
            Clock.schedule_once(lambda _, value=message: self.failure(value))

    def finish_android(self):
        try:
            self.limit_event.cancel()
            self.recorder.stop()
            data = self.path.read_bytes()
            if len(data) < 800:
                raise ValueError('录音太短')
            # Preserve the original Fitness M4A brand compatibility workaround.
            if data[4:8] == b'ftyp':
                data = data[:8] + b'M4A ' + data[12:]
            self.finish(data, 'm4a')
        except Exception:
            self.failure('录音太短或无法保存，请重试')
        finally:
            if self.recorder:
                self.recorder.release()
                self.recorder = None
            self.path.unlink(missing_ok=True)

    def reset(self):
        self.recording = False
        self.button.text = '[font=Symbols]♪[/font]'
        self.button.background_color = (.105, .112, .118, 1)

    def finish(self, data, format):
        self.reset()
        if not self.cancelled and not self.chat.closed:
            self.chat.send_audio(audio_message(data, format))

    def failure(self, message):
        self.reset()
        if not self.cancelled and not self.chat.closed:
            self.chat.notice(message)

    def cancel(self):
        self.cancelled = True
        self.held = False
        self.stop.set()
        if self.event:
            self.event.cancel()
        if self.recorder:
            try:
                self.recorder.stop()
            except Exception:
                pass
            self.recorder.release()
            self.recorder = None
        if hasattr(self, 'limit_event'):
            self.limit_event.cancel()
        self.reset()
