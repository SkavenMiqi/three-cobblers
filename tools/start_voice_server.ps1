$ErrorActionPreference = 'Stop'
$env:HF_HOME = 'F:\TalkAppEnvs\huggingface'
$env:HF_HUB_OFFLINE = '1'
$env:TALKAPP_VOICE_TMP = 'F:\TalkAppEnvs\voice-tmp'
& 'F:\TalkAppEnvs\voice\Scripts\python.exe' 'F:\Works\Python\talkApp\tools\voice_input_server.py' --cache 'F:/TalkAppEnvs/voice-models'
if ($LASTEXITCODE -ne 0) { throw 'Voice recognition server failed' }
