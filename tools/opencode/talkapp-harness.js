export default {
  id: "talkapp.harness",
  async setup(ctx) {
    await ctx.tool.transform((editor) => {
      editor.add({
        name: "talkapp_harness_guide",
        description: "Get instructions for connecting or reconnecting the TalkApp Android app, deploying its LAN Harness backend, or checking whether phone chat sync works. Use when the user asks about 手机 TalkApp / Harness 配对 / 对话同步.",
        options: { codemode: true },
        input: { type: "object", properties: {}, additionalProperties: false },
        async execute() {
          return { content: [
            "TalkApp 通过独立 Harness 后台连接手机，OpenCode 的服务端口保持在本机。",
            "已有局域网配对：先检查 TalkApp 数据目录（默认 ~/.talkapp）的 harness-host/lan-phone.json 是否存在，以及 TCP 47632 是否由 TalkApp 后台监听。若后台停了，用原本确认的工程目录重启原后台；不用无线调试或重扫。",
            "首次连接：让用户打开手机 TalkApp 并授权无线调试。运行 adb devices -l，再运行 adb shell run-as org.skaven.talkapp cat files/harness-first-setup.txt。多台设备时先选定用户授权的手机并加 adb -s <序列号>。直接读取手机清单，不让用户复制；新版手机也附带轻量后台压缩包。",
            "先确认用户要用的执行后台和工作目录，再按清单部署。连接后通过 client-config.json 和最新 chat-*.json 核对自动配置和被动同步；不要为了验证连接发模型请求，也不要输出配对凭据。",
          ].join("\n") };
        },
      });
    });
  },
};
