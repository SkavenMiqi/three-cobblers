# Android 调试包 0.2.0

产物：`bin/talkapp-0.2.0-arm64-v8a-debug.apk`，39,011,405 字节（约37.2 MiB）。
包名 `org.skaven.talkapp`，minSdk26（Android8.0），targetSdk35，arm64-v8a。
调试签名，apksigner v2校验通过；ELF架构检查未发现非ARM64库。未做真机安装/启动验证。

构建修复：Ubuntu补装libltdl-dev；lxml固定4.9.3并归档旧4.8.0生成源码；httpx/pypdf/python-docx/chardet固定兼容版本，避免下载主机架构扩展；Java显式使用当前本机代理下载Gradle依赖。工具和缓存位于F盘WSL虚拟磁盘。

重复构建：`tools/build_android.ps1`。Java代理目前为127.0.0.1:7890，需要本机代理可用。
安装后需在应用中设置模型接口，开发电脑的私人配置和历史没有打进APK。
