"""Hands-free turn-taking voice session (not full-duplex realtime audio)."""
import array
import io
import math
import threading
import time
import wave

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.modalview import ModalView
from kivy.uix.textinput import TextInput
from kivy.utils import platform

from .speech import SpeechConfig
from .storage import data_dir


def record_until_silence(cancel, finish=None, progress=None, device=None):
    """16 kHz mono WAV; finish after 1.1 s silence, bounded to 25 s."""
    if platform == 'android':
        return record_android(cancel, finish, progress)
    import sounddevice as sd
    frames = []
    started = False
    last_voice = time.monotonic()
    begin = last_voice
    with sd.RawInputStream(samplerate=16000, channels=1, dtype='int16', blocksize=1600, device=device) as stream:
        while not cancel.is_set():
            chunk, overflow = stream.read(1600)
            samples = array.array('h', bytes(chunk))
            rms = math.sqrt(sum(value * value for value in samples) / max(1, len(samples)))
            now = time.monotonic()
            if progress:
                progress(rms, now - begin, started or rms > 450)
            if rms > 450:
                started = True
                last_voice = now
            frames.append(bytes(chunk))
            if finish and finish.is_set():
                started = True
                break
            if started and now - last_voice > 1.1:
                break
            if now - begin > 25:
                break
    if cancel.is_set() or not started:
        return None
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b''.join(frames))
    return output.getvalue(), 'voice.wav'


def record_android(cancel, finish=None, progress=None):
    from jnius import autoclass
    recorder = autoclass('android.media.MediaRecorder')()
    path = data_dir() / 'voice-session.m4a'
    try:
        recorder.setAudioSource(1)
        recorder.setOutputFormat(2)
        recorder.setAudioEncoder(3)
        recorder.setAudioSamplingRate(16000)
        recorder.setOutputFile(str(path))
        recorder.prepare()
        recorder.start()
        begin = last_voice = time.monotonic()
        started = False
        while not cancel.wait(.1):
            now = time.monotonic()
            if finish and finish.is_set():
                started = True
                break
            level = recorder.getMaxAmplitude()
            if progress:
                progress(level, now - begin, started or level > 1200)
            if level > 1200:
                started, last_voice = True, now
            if (started and now - last_voice > 1.1) or now - begin > 25:
                break
        recorder.stop()
        return (path.read_bytes(), 'voice.m4a') if started and not cancel.is_set() else None
    finally:
        recorder.release()
        path.unlink(missing_ok=True)


def transcribe(audio, filename, endpoint, cancel):
    import httpx
    if cancel.is_set():
        return ''
    # The speech host uses the same local/LAN URL rules as synthesis.
    SpeechConfig(endpoint=endpoint).validate()
    with httpx.Client(timeout=60, trust_env=False) as client:
        response = client.post(endpoint, files={'file': (filename, audio)}, data={'language': 'zh'})
        response.raise_for_status()
        value = response.json().get('text', '')
    if not isinstance(value, str):
        raise ValueError('Invalid transcription response')
    return value.strip() if not cancel.is_set() else ''


class VoiceSession(ModalView):
    def __init__(self, chat, **kwargs):
        super().__init__(size_hint=(1, 1), auto_dismiss=False, **kwargs)
        self.chat = chat
        self.active = True
        self.phase = '准备中'
        self.token = threading.Event()
        self.finish_recording = threading.Event()
        self.serial = 0
        self.reply_id = None
        self.input_device = None
        self.level_feedback = None
        self.last_heard = ''
        self.recorder_done = threading.Event()
        self.recorder_done.set()
        from .legacy_widgets import surface
        from . import theme
        body = BoxLayout(orientation='vertical', padding=dp(24), spacing=dp(16))
        surface(body, theme.CHASSIS)
        body.add_widget(Label(text='VOICE / 语音对话', color=theme.VFD_CYAN, font_size=dp(20)))
        self.status = Label(text='正在准备麦克风…', font_size=dp(24))
        body.add_widget(self.status)
        self.meter = Label(text='音量 ░░░░░░░░░░  ·  0.0 秒', size_hint_y=None, height=dp(30), font_size=dp(13))
        body.add_widget(self.meter)
        self.device_button = Button(text='麦克风：系统默认（点击切换）', size_hint_y=None, height=dp(40), font_size=dp(12))
        self.device_button.bind(on_release=lambda *_: self.choose_microphone())
        body.add_widget(self.device_button)
        self.transcript = Label(text='', size_hint_y=None, height=dp(64), font_size=dp(13), halign='left')
        self.transcript.bind(size=lambda w, s: setattr(w, 'text_size', s))
        body.add_widget(self.transcript)
        self.caption = Label(text='说完稍停，我会自动接话', font_size=dp(14), halign='center')
        self.caption.bind(size=lambda w, s: setattr(w, 'text_size', (s[0], s[1])))
        body.add_widget(self.caption)
        self.finish_button = Button(text='说完了 · 停止听并识别', size_hint_y=None, height=dp(48))
        self.finish_button.bind(on_release=lambda *_: self.force_finish())
        body.add_widget(self.finish_button)
        self.retry = Button(text='打断 / 重新听', size_hint_y=None, height=dp(48))
        self.retry.bind(on_release=lambda *_: self.interrupt())
        body.add_widget(self.retry)
        exit_button = Button(text='结束对话', size_hint_y=None, height=dp(48))
        exit_button.bind(on_release=lambda *_: self.dismiss())
        body.add_widget(exit_button)
        self.add_widget(body)
        self.bind(on_dismiss=lambda *_: self.close())
        self.timer = Clock.schedule_interval(self.poll, .2)
        Clock.schedule_once(lambda _: self.prepare(), .3)

    def prepare(self):
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            def granted(permissions, results):
                Clock.schedule_once(lambda _: self.listen() if all(results) else self.fail('需要麦克风权限才能语音对话'))
            request_permissions([Permission.RECORD_AUDIO], granted)
        else:
            try:
                import sounddevice as sd
                self.device_button.text = '麦克风：' + sd.query_devices(kind='input')['name'] + '（切换）'
            except Exception:
                pass
            self.listen()

    def choose_microphone(self):
        if platform == 'android':
            self.caption.text = '安卓使用系统麦克风，请检查系统录音权限'
            return
        import sounddevice as sd
        from kivy.uix.popup import Popup
        from kivy.uix.scrollview import ScrollView
        body = BoxLayout(orientation='vertical', spacing=dp(6))
        scroll = ScrollView()
        items = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(4))
        items.bind(minimum_height=items.setter('height'))
        popup = Popup(title='选择实际使用的麦克风', content=body, size_hint=(.94, .75))
        for index, device in enumerate(sd.query_devices()):
            if device['max_input_channels'] < 1:
                continue
            control = Button(text=device['name'], size_hint_y=None, height=dp(44), font_size=dp(12))
            def select(_, value=index, name=device['name']):
                self.input_device = value
                self.device_button.text = '麦克风：' + name
                popup.dismiss()
                self.interrupt()
            control.bind(on_release=select)
            items.add_widget(control)
        scroll.add_widget(items)
        body.add_widget(scroll)
        close = Button(text='取消', size_hint_y=None, height=dp(40))
        close.bind(on_release=lambda *_: popup.dismiss())
        body.add_widget(close)
        popup.open()

    def listen(self):
        if not self.active:
            return
        self.token = threading.Event()
        self.finish_recording = threading.Event()
        self.serial += 1
        serial, token, finish = self.serial, self.token, self.finish_recording
        self.phase = 'listening'
        self.status.text = '正在听…'
        self.caption.text = '说完停顿约一秒，自动发送'
        self.level_feedback = None
        self.meter.text = '音量 ░░░░░░░░░░  ·  0.0 秒'
        def progress(level, seconds, detected):
            self.level_feedback = (serial, level, seconds, detected)
        def worker():
            try:
                recording = record_until_silence(token, finish, progress, self.input_device)
                if token.is_set():
                    return
                if not recording:
                    Clock.schedule_once(lambda _: self.no_audio(serial))
                    return
                Clock.schedule_once(lambda _: self.processing(serial))
                endpoint = self.endpoint()
                text = transcribe(*recording, endpoint, token)
                Clock.schedule_once(lambda _, value=text: self.received(serial, value))
            except Exception:
                Clock.schedule_once(lambda _: self.failure_if_current(serial))
            finally:
                self.recorder_done.set()
        self.recorder_done.clear()
        threading.Thread(target=worker, daemon=True).start()

    def endpoint(self):
        path = data_dir() / 'voice-input-url.txt'
        return path.read_text(encoding='utf-8').strip() if path.exists() else 'http://127.0.0.1:50002/v1/audio/transcriptions'

    def force_finish(self):
        if self.active and self.phase == 'listening':
            self.finish_recording.set()
            self.status.text = '正在停止录音…'
            self.caption.text = '将识别刚才录到的声音，不会丢弃录音'

    def processing(self, serial):
        if self.active and serial == self.serial:
            self.phase = 'transcribing'
            self.status.text = '录音已结束 · 正在识别…'
            self.caption.text = '录音已交给本地语音识别服务，请稍候'

    def no_audio(self, serial):
        if self.active and serial == self.serial:
            self.phase = 'error'
            self.status.text = '没有检测到有效说话声'
            self.caption.text = '请查看音量条是否变化，确认麦克风，或点击重新听后用“说完了”手动提交'

    def received(self, serial, text):
        if not self.active or serial != self.serial:
            return
        if not text:
            self.phase = 'error'
            self.status.text = '收到录音，但没有识别出文字'
            self.caption.text = '请确认麦克风有声音，点重新听再试'
            return
        self.last_heard = text
        self.transcript.text = '已听到：' + text
        self.caption.text = text
        self.status.text = '思考中…'
        self.phase = 'thinking'
        self.chat.input.text = text
        self.chat.send()
        self.reply_id = self.chat.reply_id
        if not self.chat.busy:
            self.fail('聊天未发送，请先配置可用的模型')

    def poll(self, _):
        if not self.active:
            return False
        self.finish_button.disabled = self.phase != 'listening' or self.finish_recording.is_set()
        feedback = self.level_feedback
        if self.phase == 'listening' and feedback and feedback[0] == self.serial:
            _, level, seconds, detected = feedback
            bars = min(10, max(0, round(level / 150)))
            self.meter.text = '音量 ' + '▮' * bars + '░' * (10 - bars) + f'  ·  {seconds:.1f} 秒'
            self.status.text = '检测到声音 · 正在录音' if detected else '等待声音…'
            if seconds > 3 and level < 30:
                self.caption.text = '当前声音很小或无输入，请确认上方选择的是实际麦克风'
        if self.phase == 'thinking' and not self.chat.busy:
            node = self.chat.history.node(self.reply_id)
            if not node or node['state'] != 'complete':
                return self.fail('回答未完成，点重新听继续')
            self.phase = 'speaking'
            self.status.text = '正在回答…'
            self.caption.text = node['text'][:260]
            self.chat.speaker.speak(node['text'])
        if self.phase == 'stopping' and not self.chat.busy:
            self.listen()

    def speaker_status(self, text):
        if not self.active or self.phase != 'speaking':
            return
        if text == '朗读完成':
            self.phase = 'waiting'
            Clock.schedule_once(lambda _: self.restart(self.serial), .5)
        elif any(word in text for word in ('失败', '缺少', '不可用', '无法', '没有')):
            self.fail('语音输出不可用，点重新听继续')

    def restart(self, serial):
        if self.active and serial == self.serial:
            if not self.recorder_done.is_set():
                Clock.schedule_once(lambda _: self.restart(serial), .15)
                return
            self.listen()

    def failure_if_current(self, serial):
        if self.active and serial == self.serial:
            self.fail('无法录音或连接识别服务，请检查电脑服务地址')

    def fail(self, text):
        self.phase = 'error'
        self.status.text = '暂时没接上'
        self.caption.text = text
        # One inline setup instead of nested settings menus.
        if not hasattr(self, 'address'):
            self.address = TextInput(text=self.endpoint(), multiline=False, size_hint_y=None, height=dp(44), font_size=dp(12))
            self.children[0].add_widget(self.address, index=2)

    def interrupt(self):
        if hasattr(self, 'address'):
            value = self.address.text.strip()
            try:
                SpeechConfig(endpoint=value).validate()
            except ValueError:
                return self.fail('请填写有效的本机或局域网识别服务地址')
            (data_dir() / 'voice-input-url.txt').write_text(value, encoding='utf-8')
        self.serial += 1
        self.token.set()
        self.chat.speaker.stop(notify=False)
        if self.chat.busy:
            self.chat.cancel.set()
            self.phase = 'stopping'
            self.status.text = '正在打断…'
        else:
            # Allow the old recording stream to release the microphone.
            self.phase = 'waiting'
            Clock.schedule_once(lambda _: self.restart(self.serial), .4)

    def close(self):
        self.active = False
        self.serial += 1
        self.token.set()
        self.timer.cancel()
        self.chat.speaker.stop(notify=False)
        if self.chat.busy:
            self.chat.cancel.set()
