# Reverie CLI 中文 README

Reverie CLI 是一个面向大型代码仓库的 AI 命令行工程助手。它把代码索引、上下文检索、会话记忆、检查点回滚、多模型接入和富终端交互整合到一起，让代理基于真实仓库状态工作，而不是只靠模型记忆猜测。

## 主要能力

- `Context Engine`：支持符号索引、依赖分析、语义检索、提交历史学习和工作区记忆
- 多工作模式：`Reverie`、`Reverie-Atlas`、`Reverie-Gamer`、`Reverie-Ant`、`Spec-Driven`、`Spec-Vibe`、`Writer`、`Computer Controller`
- 多模型源：标准 OpenAI 兼容接口，以及 `iFlow`、`Qwen Code`、`Gemini CLI`、`Codex`、`NVIDIA`
- 终端体验：帮助浏览器、命令选择器、状态面板、会话管理、检查点回滚、流式输出
- 安全边界：工作区路径限制、命令执行审计、归档解压防穿越
- 扩展能力：游戏开发工具链、`Reverie Engine` 内置运行时、可选的 `/tti` 文生图能力

## 安装

建议使用 Python `3.10` 或 `3.11`。

```bash
git clone https://github.com/raiden/reverie-cli.git
cd reverie-cli

python -m venv .venv
.venv\Scripts\activate

pip install -e .
```

可选安装：

```bash
pip install -e ".[dev]"
pip install -e ".[treesitter]"
pip install -r requirements-tti.txt
```

## 快速开始

```bash
reverie
reverie /path/to/project
reverie --index-only
reverie --no-index
reverie --version
```

首次运行时，至少需要配置一个模型来源。常用命令包括：

```text
/help
/status
/model
/mode
/workspace
/codex
/index
/sessions
/rollback
```

## 运行目录与配置

Reverie 会把运行时数据保存在 `app_root` 下，而不是保存在你启动命令时所在的目录里。

- 源码运行时，`app_root` 是仓库根目录
- 打包后的 Windows 版本里，`app_root` 是 `reverie.exe` 所在目录

每个项目都会在下面生成独立缓存目录：

- 全局配置：`<app_root>/.reverie/config.json`
- 项目缓存根目录：`<app_root>/.reverie/project_caches/<project-key>/`
- 工作区配置：`<app_root>/.reverie/project_caches/<project-key>/config.json`
- 规则文件：`<app_root>/.reverie/project_caches/<project-key>/rules.txt`
- 常见运行数据：`context_cache/`、`sessions/`、`archives/`、`checkpoints/`、`specs/`、`steering/`、`security/`

`<project-key>` 由项目绝对路径和短哈希生成，用来隔离不同工作区。

`<app_root>/.reverie/config.json` 是工作区模式关闭时使用的默认配置；项目缓存里的 `config.json` 是工作区模式开启时使用的工作区配置。

旧版本里的 `project_caches/<project-key>/config.global.json`、工作区本地 `.reverie/config.json`、`rules.txt` 等文件仍会在首次加载时读取迁移。新的全局写入会落到 `.reverie/config.json`，工作区写入会留在 `.reverie/project_caches/` 中。

常用配置命令：

```text
/workspace
/workspace enable
/workspace disable
/workspace copy-to-workspace
/workspace copy-to-global
```

## 文档导航

- [英文 README](../README.md)
- [英文文档入口](README.md)
- [配置说明](CONFIGURATION.md)
- [CLI 命令参考](CLI_COMMANDS.md)
- [开发维护指南](DEVELOPMENT.md)
- [Reverie Engine 使用指南](engine/reverie_engine_user_guide.md)
- [更新日志](../changelog.md)

## 模式说明

- `Reverie`：通用工程开发模式
- `Reverie-Atlas`：先调研、先写文档、再分阶段实施的深度研究模式
- `Reverie-Gamer`：面向游戏设计、脚手架、资产与试玩迭代
- `Reverie-Ant`：强调规划、执行、验证三阶段
- `Spec-Driven` / `Spec-Vibe`：偏规格驱动的工作方式
- `Writer`：偏创作和长文档工作流
- `Computer Controller`：通过 NVIDIA 模型进行桌面控制

## 维护约定

- 顶层 `README.md` 负责英文项目概览与快速上手
- `docs/README.zh-CN.md` 是中文配套说明
- 配置、路径、缓存行为变更时，需要同步更新 `docs/CONFIGURATION.md`
- 命令行为变更时，需要同步更新 `docs/CLI_COMMANDS.md` 和 `reverie/cli/help_catalog.py`
- 运行目录或 Spec/Steering 路径变更时，需要同步更新 `reverie/agent/system_prompt.py`
