# Reverie CLI 中文 README

Reverie CLI 是一个面向大型代码仓库的 AI 命令行工程助手。它把代码索引、上下文检索、会话记忆、检查点回滚、多模型接入和富终端交互整合到一起，让代理基于真实仓库状态工作，而不是只靠模型记忆猜测。

## 主要能力

- **Context Engine**：支持符号索引、依赖分析、语义检索、提交历史学习和工作区记忆
- **多工作模式**：`Reverie`、`Reverie-Atlas`、`Reverie-Gamer`、`Reverie-Ant`、`Spec-Driven`、`Spec-Vibe`、`Writer`、`Computer Controller`，所有模式共享 Context Engine，但各自的工具和工作流不同
- **多模型源**：标准 OpenAI 兼容接口，以及 `Qwen Code`、`Gemini CLI`、`Codex`、`NVIDIA`
- **终端体验**：帮助浏览器、命令选择器、状态面板、会话管理、检查点回滚、流式输出
- **安全边界**：工作区路径限制、命令执行审计、归档解压防穿越
- **扩展能力**：游戏开发工具链、`Reverie Engine` 内置运行时、可选的 `/tti` 文生图能力

## 最新更新

当前稳定版本：`v2.1.21`。

- 最新未发布改动已经加入单轮提示词执行能力，支持 `reverie -p "<任务>"`、`--mode` 以及打包后的 `Reverie.exe -p "<任务>"`。
- `Reverie-Atlas` 现在会把过于简单的任务主动切回基础 `Reverie`，`Writer` 也会优先补齐风格、篇幅、受众等写作 brief。
- 文档入口和 Gamer 路线图已经整理，旧的顶层建模说明路径已下沉到 `docs/engine/` 作为规范入口。

完整版本说明见 [更新日志](changelog.md)。

## 游戏创建功能更新预期

截至 **2026-04-06**，`Reverie-Gamer` 的目标是：

`一句提示词 -> 结构化请求 -> 蓝图 -> 运行时感知项目骨架 -> 首个可验证可玩切片 -> 持续扩展`

当前预估节奏：

- **2026-04-06 到 2026-04-20**：补强一句提示词到项目计划、里程碑和核心 artifacts 的产出闭环
- **2026-04-20 到 2026-05-11**：补强资产流水线、运行时交付规划与核心玩法系统包
- **2026-05-11 到 2026-06-08**：推进多区域扩展、续作能力和更强的验证闭环

更完整的升级计划见 [Reverie-Gamer 大型 3D 游戏升级路线图](reverie_gamer_3d_game_generation_assessment.md)。

## 安装

建议使用 Python `3.10` 或 `3.11`。

```bash
git clone https://github.com/Lin-Silver/Reverie-Cli.git
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
reverie                      # 在当前目录启动
reverie /path/to/project     # 指定项目目录启动
reverie --index-only         # 仅构建索引后退出
reverie --no-index           # 启动时跳过索引
reverie -p "修复失败测试"      # 非交互执行一轮任务后退出
reverie /path/to/project -p "新增健康检查" --mode reverie-atlas
reverie --version            # 打印版本号
```

首次运行时，至少需要配置一个模型来源。使用 `/model` 添加预设，或使用 `/qwencode`、`/Geminicli`、`/codex`、`/nvidia` 进行特定模型源配置。

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `/help` | 浏览命令目录 |
| `/status` | 查看当前模型、来源、会话和运行状态 |
| `/model` | 管理标准模型预设 |
| `/mode` | 查看或切换工作模式 |
| `/codex` | 激活 Codex 并选择模型/推理深度 |
| `/search <query>` | 执行网络搜索 |
| `/index` | 重建工作区索引 |
| `/tools` | 列出当前模型可见的工具 |
| `/sessions` | 浏览会话 |
| `/rollback` | 恢复检查点或交互状态 |
| `/clean` | 清除当前工作区的内存、缓存和审计数据 |

完整命令参考见 [docs/CLI_COMMANDS.md](CLI_COMMANDS.md)。

## 工作模式

| 模式 | 说明 |
| --- | --- |
| `Reverie` | 通用代码模式，使用最小且必要的工具集 |
| `Reverie-Atlas` | 面向复杂系统的文档驱动 Spec 开发模式 |
| `Reverie-Gamer` | 面向提示词编译、蓝图生成、运行时脚手架、可玩切片与验证闭环的游戏生产模式 |
| `Reverie-Ant` | 面向长流程任务的规划、执行与验证模式 |
| `Spec-Driven` | 需求、设计与任务拆分的 Spec 编写模式 |
| `Spec-Vibe` | 执行已批准 Spec 的轻量实现模式 |
| `Writer` | 创作与叙事连续性模式 |
| `Computer Controller` | 通过 `computer_control` 进行桌面控制 |

## 运行目录与配置

Reverie 会把运行时数据保存在 `app_root` 下，而不是保存在你启动命令时所在的目录里。详细配置说明见 [docs/CONFIGURATION.md](CONFIGURATION.md)。

- 源码运行时，`app_root` 是仓库根目录
- 打包后的 Windows 版本里，`app_root` 是 `reverie.exe` 所在目录
- 每个项目会在 `<app_root>/.reverie/project_caches/<project-key>/` 生成独立缓存目录

常用配置命令：

```text
/workspace
/workspace enable
/workspace disable
/workspace copy-to-workspace
/workspace copy-to-global
```

## 开发

```bash
pip install -e ".[dev]"
mypy reverie
black reverie
```

Windows 打包：

```bat
.\build.bat
.\build.bat --recreate-venv
.\build.bat --test-exe
```

生成的 `dist/reverie.exe` 现在会把 Reverie-Gamer 的内置运行时能力一起打进单文件里，包括 `/engine video`、`/engine renpy` 和 `/modeling primitive`。如果构建时能找到 `ffmpeg`，`build.bat` 会把它一起打包进 exe，这样 `mp4/gif` 导出不需要额外安装编码器；如果找不到，帧序列导出仍然可用，视频编码则会在运行时回退到外部 `ffmpeg`。

## 文档导航

- [English README](../README.md)
- [文档入口](README.md)
- [配置说明](CONFIGURATION.md)
- [CLI 命令参考](CLI_COMMANDS.md)
- [开发维护指南](DEVELOPMENT.md)
- [Reverie Engine 使用指南](engine/reverie_engine_user_guide.md)
- [Reverie-Gamer 建模流程指南](engine/reverie_gamer_modeling_pipeline.md)
- [Reverie-Gamer 大型 3D 游戏升级路线图](reverie_gamer_3d_game_generation_assessment.md)
- [更新日志](changelog.md)

## 维护约定

- 顶层 `README.md` 负责英文项目概览与快速上手
- `docs/README.zh-CN.md` 是中文配套说明
- `docs/engine/` 负责 Reverie Engine 与 Reverie-Gamer 的运行时/建模专项文档
- 配置、路径、缓存行为变更时，需要同步更新 `docs/CONFIGURATION.md`
- 命令行为变更时，需要同步更新 `docs/CLI_COMMANDS.md` 和 `reverie/cli/help_catalog.py`
- 运行目录或 Spec/Steering 路径变更时，需要同步更新 `reverie/agent/system_prompt.py`
