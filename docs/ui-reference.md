# 紧凑聊天布局参考

参考 GitHub 仓库 README 中发布的官方截图：

- RikkaHub：https://github.com/rikkahub/rikkahub （docs/img/poster.png）
- Cherry Studio Mobile：https://github.com/CherryHQ/cherry-studio-app （.github/images/readme/chat.png）

借鉴信息层级和交互方式，保留本项目原有黑钛主题，不移植上述项目代码或素材。

调整：
- 取消常驻摘要和快捷操作多层栏；摘要进入顶部更多菜单。
- 快捷问题仅在空对话展示。
- 每条消息使用紧凑的角色/模型、发送时间、更多图标；编辑/重答/删除进入菜单。
- 有多个版本才显示分支切换控件；正常完成状态不重复占行。
- 消息按本地日期分段，逐条显示本地时分；详情显示完整时间和模型来源。
- 历史侧栏采用标题、更新时间两层结构，置顶/改名/删除进入更多菜单。
- 输入框默认紧凑，多行文字时增加高度。

SQLite 时间以 UTC 存储，显示时转换成本地时间。旧记录沿用已有时间字段，不编造缺失时间。
