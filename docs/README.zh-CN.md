# Reverie CLI 中文概览

2026-10-08 文档整理入口：[文档导航](README.md)、[完整版本更新记录](changelog.md)、[Intelligent UI 技术规格与 AI 开发提示词](INTELLIGENT_UI_SPEC.md)。交互视图是待开发提案，尚未实现；历史验证已集中保留。

Reverie CLI 是一个面向大型代码仓库的上下文引擎驱动 AI 助手，提供代码检索、多模型来源、会话记忆、检查点、回滚、工具调用和终端界面。

桌面端使用同一个 Python 内核，提供项目 / 会话、结构化附件、执行控制、Git 和运行证据面板。按 2026-10-06 核对后的使用入口是 [桌面指南](DESKTOP_GUIDE.md)、[功能状态与缺口](FEATURE_STATUS.md)、[Skills](SKILLS.md) 和 [文档目录](README.md)；MCP 的客户端能力边界另见 [二次源码审查](VERIFICATION_HISTORY.md#reverie-cli-feature-audit-addendum-2026-10-05)，跨平台提供者身份与多语言解析覆盖见 [第三轮源码审查](VERIFICATION_HISTORY.md#reverie-cli-platform-language-audit-2026-10-05)。后续开发统一看 [路线图](ROADMAP.md)。

## 主要能力

- 统一工作面板：拖动调整宽度，文件树浏览与 UTF-8 编辑保存；对话标题栏直接选择全部、思考与回复或仅回复。实现和实测边界见 [2026-10-06 修复报告](VERIFICATION_HISTORY.md#reverie-cli-workbench-repairs-2026-10-06)。
- 桌面个人资料：可改显示名称、上传 / 拖动 / 缩放 / 裁剪头像；用户消息在右、模型回答在左。Stop 直接中断模型连接等待，流式开关立即反馈，连续对话复用内核和健康连接；验证范围见 [请求与个人资料修复](VERIFICATION_HISTORY.md#reverie-cli-request-profile-repairs-2026-10-05)。

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

CLI 内置的 Python Reverie Engine 当前为 Alpha，与通过 RATS 连接的外部 Engine 编辑器是不同表面。Headless 游戏循环、场景、物理查询、导航、输入、存档和证据验证已经实现；ModernGL 可进行离屏网格/基础纹理渲染与 PNG 捕获。原生窗口、输入、缩放与关闭已有 Windows 实机验证；完整 PBR 渲染、原生 Live2D、高级音频及其他平台仍待完成。详细信息见 [引擎指南](engine/reverie_engine_user_guide.md)、[本轮修复报告](VERIFICATION_HISTORY.md#reverie-cli-feature-repairs-2026-10-05) 和统一的 [后续更新路线图](ROADMAP.md)。
