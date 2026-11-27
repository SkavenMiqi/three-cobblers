# 来源与第三方说明

本项目基于作者既有项目 [SkavenMiqi/fitness](https://github.com/SkavenMiqi/fitness) 的 Kivy 界面与组件演进。
黑钛主题、顶栏、部分控件与 AI 配置源自该项目；保留完整参考仓库的目录不纳入此仓库。

运行依赖包括 Kivy、Pillow、httpx、Beautiful Soup、pypdf、python-docx、lxml、cryptography、Pygments 等，权利归各自作者，按其许可证使用。
配对二维码使用 [python-qrcode](https://github.com/lincolnloop/python-qrcode)（BSD-3-Clause）生成，Android 端使用 [ZXing Core](https://github.com/zxing/zxing)（Apache-2.0）识别。
`assets/fonts/` 中字体沿用上游素材。公开发布不重新授权这些字体；完整字体来源/授权说明仍待补齐，使用或再分发前须核对相应条款。

曾参考 RikkaHub、Cherry Studio、LibreChat、Chatbox、NextChat、Hermes 的公开功能文档与交互思路，未直接引入它们的运行代码。
局域网扫码配对和多工程助手接入分别参考了 Cuplivo 和 AionUi 的公开功能说明，未引入其运行代码。
