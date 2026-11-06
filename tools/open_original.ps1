$ErrorActionPreference = 'Stop'
$env:KIVY_HOME = 'F:\TalkAppEnvs\kivy-original'
Start-Process -FilePath 'F:\TalkAppEnvs\fitness-original\Scripts\python.exe' `
    -ArgumentList 'main.py' -WorkingDirectory 'F:\Works\Python\talkApp\fitness-original'
