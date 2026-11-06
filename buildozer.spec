[app]
title = TalkApp
package.name = talkapp
package.domain = org.skaven
source.dir = .
source.include_exts = py,ttf,ttc,png,jpg
source.exclude_dirs = fitness,fitness-original,backups,tests,tools,docs,.git,.venv,.agents
source.exclude_patterns = window-preview.png
version = 0.2.0
icon.filename = assets/brand/icon.png
presplash.filename = assets/brand/presplash.png
presplash.color = #070A0D
requirements = python3,kivy==2.3.1,filetype,pillow,pyjnius,certifi,httpx==0.28.1,httpcore==1.0.9,h11,anyio==4.8.0,sniffio,typing_extensions,idna,soupsieve,beautifulsoup4==4.13.4,pypdf==5.9.0,python-docx==1.1.2,lxml==4.9.3,cryptography,pygments,chardet==5.2.0
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,RECORD_AUDIO
android.archs = arm64-v8a
android.api = 35
android.minapi = 26
android.enable_androidx = True
android.allow_backup = False
android.accept_sdk_license = True
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
