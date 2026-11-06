"""Answer playback: configurable WAV endpoint with Android/Windows TTS fallback."""
import io
import ipaddress
import json
import re
import ssl
import threading
import uuid
import urllib.request
import wave
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

import certifi
from .storage import data_dir


def spoken_text(text):
    text = re.sub(r'```[^\n]*\n.*?(?:```|$)', '（代码略）', text, flags=re.S)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(?m)^\s*(?:#{1,6}|[-*>])\s*', '', text)
    return re.sub(r'[*`_]', '', text).strip()


def sentences(text, size=240):
    parts, current = [], ''
    for part in re.split(r'(?<=[。！？!?；;\n])', text):
        while len(part) > size:
            if current:
                parts.append(current)
                current = ''
            parts.append(part[:size])
            part = part[size:]
        if len(current) + len(part) > size and current:
            parts.append(current)
            current = ''
        current += part
    if current.strip():
        parts.append(current)
    return parts


@dataclass
class SpeechConfig:
    endpoint: str = ''
    api_key: str = ''
    model: str = 'cosyvoice'
    voice: str = 'default'
    instruction: str = '用自然、温和的普通话交谈，停顿自然。'
    speed: float = 1.0
    auto_read: bool = False
    fallback: bool = True
    neural_voice: str = 'zh-CN-XiaoxiaoNeural'

    @classmethod
    def load(cls):
        try:
            value = json.loads((data_dir() / 'speech.json').read_text(encoding='utf-8'))
            return cls(**{key: val for key, val in value.items() if key in cls.__dataclass_fields__})
        except (OSError, ValueError, TypeError, AttributeError):
            return cls()

    def validate(self):
        if not .5 <= self.speed <= 2:
            raise ValueError('语速应在 0.5–2.0 之间')
        if self.endpoint:
            url = urlparse(self.endpoint)
            private = url.hostname == 'localhost'
            try:
                address = ipaddress.ip_address(url.hostname or '')
                private = address.is_private or address.is_loopback
            except ValueError:
                pass
            if not url.hostname or url.username or url.password or url.query or url.fragment or (
                    url.scheme != 'https' and not (url.scheme == 'http' and private)):
                raise ValueError('语音地址需为 HTTPS，或本机/局域网 HTTP 地址')

    def save(self):
        self.validate()
        path = data_dir() / 'speech.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding='utf-8')
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(path)


def request_wav(config, text):
    config.validate()
    body = {'input': text, 'model': config.model, 'voice': config.voice, 'speed': config.speed,
            'instructions': config.instruction, 'response_format': 'wav'}
    headers = {'Content-Type': 'application/json'}
    if config.api_key:
        headers['Authorization'] = 'Bearer ' + config.api_key
    request = urllib.request.Request(config.endpoint, data=json.dumps(body).encode('utf-8'), headers=headers)
    with urllib.request.urlopen(request, timeout=45, context=ssl.create_default_context(cafile=certifi.where())) as response:
        data = response.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise ValueError('音频过大')
    with wave.open(io.BytesIO(data)) as wav:
        if wav.getcomptype() != 'NONE' or wav.getnchannels() not in (1, 2) or wav.getnframes() == 0:
            raise ValueError('服务需返回有效 PCM WAV 音频')
    return data


class Speaker:
    def __init__(self, notify):
        self.notify = notify
        self.cancel = threading.Event()
        self.generation = 0
        self.sound = None
        self.files = set()
        self.tts = None
        self.android_queue = None
        self.closed = False

    def stop(self, notify=True):
        self.generation += 1
        self.cancel.set()
        if self.sound:
            self.sound.stop()
            self.sound.unload()
            self.sound = None
        if self.tts:
            self.tts.stop()
        if self.android_queue:
            self.android_queue.cancel()
            self.android_queue = None
        self.cleanup()
        if notify:
            self.notify('已停止朗读')

    def cleanup(self):
        for path in list(self.files):
            try:
                path.unlink(missing_ok=True)
                self.files.discard(path)
            except OSError:
                pass

    def speak(self, text):
        self.stop(notify=False)
        text = spoken_text(text)
        if not text:
            return self.notify('没有可朗读的文字')
        config = SpeechConfig.load()
        try:
            config.validate()
        except ValueError as exc:
            return self.notify(str(exc))
        self.cancel = threading.Event()
        generation, cancel = self.generation, self.cancel
        from kivy.utils import platform
        self.notify('正在生成语音…')
        def worker():
            from kivy.clock import Clock
            for part in sentences(text):
                if cancel.is_set():
                    return
                try:
                    if config.endpoint:
                        data = request_wav(config, part)
                        extension = '.wav'
                    else:
                        import asyncio
                        import edge_tts
                        async def synthesize():
                            rate = f'{round((config.speed - 1) * 100):+d}%'
                            communication = edge_tts.Communicate(part, config.neural_voice, rate=rate)
                            audio = bytearray()
                            async for event in communication.stream():
                                if cancel.is_set():
                                    return b''
                                if event['type'] == 'audio':
                                    audio.extend(event['data'])
                            return bytes(audio)
                        encoded = asyncio.run(synthesize())
                        if cancel.is_set():
                            return
                        import miniaudio
                        decoded = miniaudio.decode(encoded, output_format=miniaudio.SampleFormat.SIGNED16,
                                                   nchannels=1, sample_rate=24000)
                        output = io.BytesIO()
                        with wave.open(output, 'wb') as wav:
                            wav.setnchannels(1)
                            wav.setsampwidth(2)
                            wav.setframerate(24000)
                            wav.writeframes(decoded.samples.tobytes())
                        data = output.getvalue()
                        extension = '.wav'
                except Exception:
                    if not cancel.is_set() and config.fallback:
                        # Read the unplayed remainder only.
                        rest = text[text.find(part):]
                        Clock.schedule_once(lambda _, value=rest: self.fallback(value, config, generation))
                    elif not cancel.is_set():
                        self.notify('电脑语音服务不可用，请检查地址或打开系统兜底')
                    return
                done = threading.Event()
                Clock.schedule_once(lambda _, audio=data, event=done, ext=extension: self.play_wav(audio, generation, event, ext))
                while not done.wait(.1):
                    if cancel.is_set():
                        return
            if not cancel.is_set():
                self.notify('朗读完成')
        threading.Thread(target=worker, daemon=True).start()

    def fallback(self, text, config, generation):
        if generation == self.generation and not self.closed:
            self.notify('自然语音暂不可用，切换系统声音')
            self.system_speak(text, config, generation)

    def play_wav(self, data, generation, done, extension='.wav'):
        if generation != self.generation or self.closed:
            done.set()
            return
        from kivy.core.audio import SoundLoader
        path = data_dir() / ('tts-' + uuid.uuid4().hex + extension)
        path.write_bytes(data)
        self.files.add(path)
        sound = SoundLoader.load(str(path))
        if not sound:
            done.set()
            self.cleanup()
            self.notify('无法播放 WAV 音频')
            return
        self.sound = sound
        def finished(*_):
            sound.unbind(on_stop=finished)
            sound.unload()
            if self.sound is sound:
                self.sound = None
            self.cleanup()
            done.set()
        sound.bind(on_stop=finished)
        sound.play()
        self.notify('正在朗读…')

    def system_speak(self, text, config, generation):
        from kivy.utils import platform
        if generation != self.generation or self.closed:
            return
        if platform == 'win':
            def windows():
                try:
                    import pythoncom
                    import win32com.client
                except ImportError:
                    self.notify('Windows 朗读缺少 pywin32 组件')
                    return
                pythoncom.CoInitialize()
                try:
                    voice = win32com.client.Dispatch('SAPI.SpVoice')
                    # Prefer an installed Chinese voice instead of an English default.
                    for item in voice.GetVoices():
                        if any(code in str(item.GetAttribute('Language')).lower().split(';') for code in ('804', '404', 'c04')):
                            voice.Voice = item
                            break
                    voice.Rate = max(-5, min(5, round((config.speed - 1) * 5)))
                    for part in sentences(text):
                        if generation != self.generation or self.closed:
                            return
                        voice.Speak(part, 1)
                        while not voice.WaitUntilDone(100):
                            if generation != self.generation or self.closed:
                                voice.Speak('', 3)
                                return
                    self.notify('朗读完成')
                except Exception:
                    self.notify('系统朗读失败，请检查已安装的中文语音')
                finally:
                    pythoncom.CoUninitialize()
            self.notify('系统朗读中…')
            threading.Thread(target=windows, daemon=True).start()
        elif platform == 'android':
            try:
                self.android_speak(text, config, generation)
            except Exception:
                self.notify('系统朗读不可用，请检查中文语音引擎')
        else:
            self.notify('此系统尚未接入默认朗读，请配置电脑语音服务')

    def android_speak(self, text, config, generation):
        from jnius import autoclass, PythonJavaClass, java_method
        from kivy.clock import Clock
        owner = self
        class Listener(PythonJavaClass):
            __javainterfaces__ = ['android/speech/tts/TextToSpeech$OnInitListener']
            __javacontext__ = 'app'

            @java_method('(I)V')
            def onInit(self, status):
                Clock.schedule_once(lambda _: owner.android_ready(status, text, config, generation))
        self.listener = Listener()
        activity = autoclass('org.kivy.android.PythonActivity').mActivity
        if self.tts:
            self.tts.shutdown()
        self.tts = autoclass('android.speech.tts.TextToSpeech')(activity, self.listener)

    def android_ready(self, status, text, config, generation):
        if generation != self.generation or self.closed:
            return
        if status != 0:
            return self.notify('系统语音初始化失败，请安装中文语音引擎')
        from jnius import autoclass
        from kivy.clock import Clock
        result = self.tts.setLanguage(autoclass('java.util.Locale').SIMPLIFIED_CHINESE)
        if result < 0:
            return self.notify('系统缺少中文语音数据，请在系统设置中安装')
        self.tts.setSpeechRate(float(config.speed))
        queue = sentences(text, size=1500)
        started = [False]
        def next_part(_):
            if generation != self.generation or self.closed:
                return False
            if self.tts.isSpeaking():
                return
            if queue:
                code = self.tts.speak(queue.pop(0), 0, None, str(uuid.uuid4()))
                if code < 0:
                    self.notify('系统朗读失败')
                    return False
                started[0] = True
            elif started[0]:
                self.notify('朗读完成')
                return False
        self.notify('系统朗读中…')
        self.android_queue = Clock.schedule_interval(next_part, .3)

    def close(self):
        self.closed = True
        self.stop(notify=False)
        if self.tts:
            self.tts.shutdown()
