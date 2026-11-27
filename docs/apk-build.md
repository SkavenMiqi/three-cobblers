# Android 调试包 1.0.0

产物：`bin/talkapp-1.0.0-arm64-v8a-debug.apk`。面向用户的 APK 发布在 [GitHub Releases](https://github.com/SkavenMiqi/three-cobblers/releases/tag/v1.0.0)。
包名 `org.skaven.talkapp`，minSdk26（Android8.0），targetSdk35，arm64-v8a。
该产物使用 Android 调试签名；不是应用商店签名包。

构建修复：Ubuntu补装libltdl-dev；lxml固定4.9.3并归档旧4.8.0生成源码；httpx/pypdf/python-docx/chardet固定兼容版本，避免下载主机架构扩展；Java显式使用当前本机代理下载Gradle依赖。工具和缓存位于F盘WSL虚拟磁盘。

重复构建：`tools/build_android.ps1`。Java代理目前为127.0.0.1:7890，需要本机代理可用。
安装后需在应用中设置模型接口，开发电脑的私人配置和历史没有打进APK。
