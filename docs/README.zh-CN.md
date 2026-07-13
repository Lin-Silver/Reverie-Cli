# Reverie CLI 中文概览

Reverie CLI 是一个面向大型代码仓库的上下文引擎驱动 AI 助手，提供代码检索、多模型来源、会话记忆、检查点、回滚、工具调用和终端界面。

## 主要能力

- `Reverie`：通用代码、自动化和仓库任务。
- `Reverie-Atlas`：文档驱动的规格、设计和交付流程。
- `Reverie-Gamer`：仍在完善中的游戏规划、项目生成、垂直切片和运行证据验证。
- `Writer`：磁盘持久化的长篇写作、连续性检查和完成审计。
- `Computer Controller`：Windows 桌面控制与受管子代理。
- Context Engine：符号、依赖、语义、提交历史和项目记忆检索。

## 安装

```bash
cd ReverieCli-py
pip install -e .
reverie
```

支持 Python 3.10–3.14。完整配置和命令请参阅 [配置指南](CONFIGURATION.md) 与 [CLI 命令](CLI_COMMANDS.md)。

## 游戏运行时边界

Reverie Engine 当前为 Alpha。Headless 游戏循环、场景、物理查询、导航、输入、存档和证据验证已经实现；ModernGL 可进行离屏网格/基础纹理渲染与 PNG 捕获。桌面窗口呈现、完整 PBR 渲染、原生 Live2D 和高级音频仍在计划中。详细信息见 [引擎指南](engine/reverie_engine_user_guide.md) 和统一的 [后续更新路线图](ROADMAP.md)。
