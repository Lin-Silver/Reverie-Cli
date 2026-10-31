# Reverie CLI 中文概览

使用入口：[文档导航](README.md)、[桌面指南](DESKTOP_GUIDE.md)、[版本更新记录](changelog.md)。

Desktop 支持内联、全屏和画中画交互视图，以及指标卡、表格和图文推荐等富格式回答。

Reverie CLI 是一个面向大型代码仓库的上下文引擎驱动 AI 助手，提供代码检索、多模型来源、会话记忆、检查点、回滚、工具调用和终端界面。

桌面端使用同一个 Python 内核，提供项目 / 会话、结构化附件、执行控制、Git 和运行证据面板。

## 主要能力

- 统一工作面板：拖动调整宽度，浏览文件树、编辑 UTF-8 文件、审查 Git 改动和使用终端。
- 桌面个人资料：上传和裁剪头像；用户消息在右、模型回答在左，用户消息标题只显示头像。
- `Reverie`：通用代码、自动化和仓库任务。
- `Reverie-Atlas`：文档驱动的规格、设计和交付流程。
- `Reverie-Gamer`：仍在完善中的游戏规划、项目生成、垂直切片和运行证据验证。
- `Writer`：磁盘持久化的长篇写作、连续性检查和完成审计。
- `Computer Controller`：Windows 桌面控制与受管子代理。
- Context Engine：符号、依赖、语义、提交历史和项目记忆检索。
- 图片生成：可在桌面端「设置 → 生图模型」选择本地或远程模型。Pollinations 生图需要 API 密钥；SenseNova 图片编辑默认由服务决定输出尺寸，可通过 `size` 指定尺寸。
- Skills：渐进式 `SKILL.md` 发现；`/skill <名称>` 固定必须使用的 Skill，每轮完整读取主正文并注入请求，缺失时阻止执行。内置 `photo-to-3d` 与 Emil Kowalski 的全部 14 个设计 Skill（含 Apple Design）。CLI / Desktop 重启、同任务分叉 / 轮换可恢复 pin；普通新会话独立。模型实际遵循和引用资源的边界见 [Skills 指南](SKILLS.md)。

## 安装

```bash
cd ReverieCli-py
pip install -e .
reverie
```

支持 Python 3.10–3.14。完整配置和命令请参阅 [配置指南](CONFIGURATION.md) 与 [CLI 命令](CLI_COMMANDS.md)。

指定项目使用 `reverie "G:\Projects\MyProject"`，临时来源 / 模型使用 `--source` / `--model`，调试使用 `--debug`。核心默认配置与会话保存在 app-root 的 `.reverie`；工作区中的桌面日志 / 附件和 Electron 草稿存储是另外的位置，备份时需分别处理。

Windows 可使用安装包或便携包；「设置 → 关于」显示构建 ID、构建时间和实际启动路径，旧安装快捷方式不会因下载新便携包而更新。首次便携启动包含运行时解压。提供商文本探测要求有效文本，但不能证明 SSE、工具或视觉理解兼容。

## 游戏运行时边界

CLI 内置的 Python Reverie Engine 当前为 Alpha，与通过 RATS 连接的外部 Engine 编辑器是不同表面。 Headless 游戏循环、场景、物理查询、导航、输入、存档和证据验证已经实现；ModernGL 可进行离屏网格/基础纹理渲染与 PNG 捕获。 原生窗口、输入、缩放与关闭已有 Windows 实机验证；完整 PBR 渲染、原生 Live2D、高级音频及其他平台仍待完成。
