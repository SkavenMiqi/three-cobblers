# 自然语音与系统朗读

## 当前主入口：连续语音对话

底部音符按钮现在打开独立语音会话，不再打开系统转写弹窗。自动录音、停顿约1.1秒识别、自动发送、自动播放回答，播放完成后继续录音。录音单次最长25秒。支持按钮打断/重新听与退出，不支持用户说话自动打断的全双工模式。错误时界面内显示识别服务地址，可修改后重新听。

本机识别环境：`F:\TalkAppEnvs\voice`；模型缓存：`F:\TalkAppEnvs\voice-models`。
faster-whisper small CPU int8，已完成真实中文测试音频识别。Windows 兼容版本记录在 `tools/voice_requirements.txt`。
启动识别服务：`.\tools\start_voice_server.ps1`，默认 `127.0.0.1:50002`。本机运行客户端可直接使用默认值。
手机需要在电脑启动服务时指定 `--host 0.0.0.0` 并填电脑局域网IP，不能使用手机的127.0.0.1；当前服务仅供受信局域网使用，没有鉴权，不应暴露公网。Android 录音权限和音频链路仍需真机验证。

桌面录音使用系统默认输入设备；本机检测到 PicoStreamingMicrophone，需在 Windows 声音设置中选择实际使用的麦克风。
声音输出暂用系统中文音色（或已经配置的 WAV 服务），自然音色 CosyVoice 还未部署。回答需模型生成完再开始播放，非实时音频模型。
用户与AI的语音文字保存在当前聊天；原始录音只用于转写，不作为历史附件保存。

验证：`tools/verify_voice_session.py` 模拟循环和退出，`tools/verify_voice_roundtrip.py` 使用真实本机转写服务。

## 当前客户端

回答的 `⋮ → 朗读回答`；顶部 `⋮ → 语音与朗读` 可保存设置、试听、控制自动朗读和系统兜底。
顶部/消息菜单均可停止朗读。发送新问题、关闭应用时停止旧播放。
默认使用 Windows SAPI / Android TextToSpeech，中文音色由系统已安装语音引擎决定。
Android 分段播放、语言数据检测已实现，尚需真机验证。当前为回答结束后朗读，非实时全双工语音。

电脑语音接口使用完整 URL，如 `http://192.168.1.2:50001/v1/audio/speech`。
客户端发送 `input/model/voice/speed/instructions/response_format` JSON，要求返回 PCM WAV。
语音配置独立于聊天 API；密钥为私有 JSON 存储，尚未 Keystore 加密。
内容按句切块，逐块合成播放。停止后未完成的网络请求不会强行终止，但其音频不会继续播放。
连接失败时可使用系统朗读剩余内容。当前不做音频流式解码，需等每一块生成完才播放。

## 开源模型调研

核对了以下上游 README（不是本机试听结论）：

- [CosyVoice](https://github.com/FunAudioLLM/CosyVoice)：中文、自然韵律、零样本参考音色，支持指令控制和流式推理。优先候选。
- [F5-TTS](https://github.com/SWivid/F5-TTS)：中文/英文参考音色和多风格推理，代码 MIT，官方预训练模型标注 CC-BY-NC，作为试听对照候选。

上游公布延迟并非本机性能保证；自然度需用同一中文样稿实际试听。尚未下载模型权重，也未安装 GPU 推理依赖。

## CosyVoice 电脑桥接

在 F 盘准备独立的 CosyVoice 仓库、Python 环境和权重，按上游 README 安装，避免覆盖 TalkApp 运行环境。
桥接代码为 `tools/cosyvoice_bridge.py`，直接调用上游 `AutoModel`。上游原生 FastAPI 接口返回裸 PCM、使用表单，不能直接填入客户端的 WAV JSON 接口。

在已安装 CosyVoice 的环境运行（路径按实际修改）：

```powershell
$env:TALKAPP_VOICE_TOKEN = '你设置的服务密钥'
python tools/cosyvoice_bridge.py --repo F:/Voice/CosyVoice --model-dir F:/Voice/models/CosyVoice --reference-audio F:/Voice/reference.wav --reference-text '参考音频中实际说出的文字' --host 0.0.0.0 --port 50001
```

手机与电脑同一局域网时填电脑局域网 IP，voice 填 `default`，密钥与服务端一致。只暴露配置的一份参考音色。
如需复现参考音色而不使用指令模式，可将客户端“语气描述”留空。外出访问的连接方式后续配置。

启动前确认上游模型版本支持相应的 zero_shot/instruct2 方法；桥接尚未与真实权重联调。不要将本地系统朗读效果当作 CosyVoice 模型效果。
