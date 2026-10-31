# Reverie CLI 文档导航

2026-10-28 GitHub 接续更新：用户已明确授权将本轮全部仓库改动提交到新的 `dev` 分支；本轮授权覆盖此前禁止提交/推送的限制，不含版本升级或 Release。[接续说明](CONTINUE_RIU.md)与[可克隆 goal/关键证据](verification/2026-10-28-dev-handoff/README.md)已补齐。**最新源码还包含保留 v12 之后的 Linux 安装链接启动器修复；它的回归测试已有覆盖，但包含此修复的新安装包尚未验收，优先完成此项。** 此前 v12 通过记录仅对应原包；整体 RIU 仍未完成。实际提交 SHA 与远端推送结果以交付消息及 GitHub 分支为准。

当前总体 RIU 仍在实施中，三端安装包与完整模型质量验收尚未完成。已批准的范围、进度及完成标准见[完整实施清单](RIU_COMPLETION_PLAN.md)。[2026-10-25 实施快照](verification/2026-10-25-full-riu/README.md)记录构建 `85ab811e5ef12ec9`、Linux deb实际安装/升级/卸载、AppImage运行验证及已收尾但未达标的第2整组60项矩阵、175项校验器回归和最终请求审计。下方富格式 UI 记录为上一阶段的已验证快照。


上一阶段（2026-10-25）：已按用户参考图实现**回答 UI/UX 与格式样式**：统计卡片、状态表格、图文推荐、来源与链接，支持深浅主题、窄容器、流式输出和会话重开。[格式说明](RICH_ANSWER_UI.md)与[实际原生截图和验证](verification/2026-10-25-rich-answer-ui/README.md)已记录。当时 Linux 包 **c9df6ba5417e0851**；Desktop **407/1**、Python **2314/24**、类型检查通过，该阶段包原生 P2/P3/隔离 **24/26/36** 通过。真实模型回答及两张远程图片实际显示成功，完整 27 工具和采样设置保留。旧正式矩阵依最新优先级停在 15 项，不宣称完成 36 项或整体模型质量验收。

2026-10-24 更新。先按问题选入口，避免把历史规格、测试记录和当前能力混为一谈。本轮源码与 Linux 原生打包范围见[最新验证](VERIFICATION_HISTORY.md#riu-completion-2026-10-22)，旧模型质量矩阵作为部分历史记录保留，本轮优先验收回答展示。

| 想了解什么 | 唯一主要入口 |
| --- | --- |
| 统计卡片、图文推荐、状态标签与来源格式 | [富格式回答](RICH_ANSWER_UI.md) |
| 安装、启动、项目概览 | [English README](../README.md) / [中文快速上手](README.zh-CN.md) |
| 当前能做什么、已知缺口与未验证范围 | [FEATURE_STATUS](FEATURE_STATUS.md) |
| 下一步做什么、完成条件是什么 | [ROADMAP](ROADMAP.md) |
| ChatGPT 类交互视图怎么开发、下一步给 AI 什么提示词 | [INTELLIGENT_UI_SPEC](INTELLIGENT_UI_SPEC.md) — 已实现宿主、协议范围与待通过的模型质量门 |
| 各版本到底改了什么 | [changelog](changelog.md) — 40 个版本入口、发布后更新、Unreleased 和历史例外 |
| 过去具体测过什么 | [VERIFICATION_HISTORY](VERIFICATION_HISTORY.md) — 原日期、主机、测量、失败与限制 |
| 当前 RIU 的目标、完成进度与剩余门槛 | [RIU 完成计划](RIU_COMPLETION_PLAN.md) / [当前源码 Linux 证据](verification/2026-10-27-static-rich-routing/README.md) / [结构化包验收](verification/2026-10-27-static-rich-routing/package-rebuilds.json) |
| 过去为什么这样设计 | [DEVELOPMENT_HISTORY](DEVELOPMENT_HISTORY.md) — S01–S21、Codex 比较、旧提示词和 RATS 交接 |

## 使用与配置

| 指南 | 内容 |
| --- | --- |
| [Desktop](DESKTOP_GUIDE.md) | 输入、指令、工作面板、文件编辑、显示选项、执行与恢复 |
| [CLI commands](CLI_COMMANDS.md) | 终端命令、参数、模型、会话、工具与专用模式 |
| [Configuration](CONFIGURATION.md) | 配置与存储、模型提供者、MCP、图像/视频与 Atlas |
| [Skills](SKILLS.md) | 发现、固定、完整正文读取、持久化与内置技能 |
| [Context Engine memory](CONTEXT_ENGINE_MEMORY.md) | 项目记忆、检索、来源、冲突与版本；历史检索测量见验证历史 |
| [SubAgents](SUBAGENTS.md) | 委派、隔离、会话与日志 |
| [Computer Controller](COMPUTER_CONTROLLER.md) | 桌面观察、动作与工作流 |
| [Writer](writer_mode.md) | 长篇项目、连续性与恢复 |
| [RATS / RTP](RATS_RTP.md) | 本地服务发现、权限会话、目录与动态工具 |
| [Security permissions](SECURITY_PERMISSIONS.md) | 权限级别、禁用操作与信任边界 |

## 开发与 Engine

| 指南 | 内容 |
| --- | --- |
| [Development](DEVELOPMENT.md) | 环境、检查命令、打包与文档维护规范 |
| [Harness engineering](HARNESS_ENGINEERING.md) | Prompt、上下文、工具执行与验证纪律 |
| [Engine user guide](engine/reverie_engine_user_guide.md) | 内置运行时、内容模型与 `/engine` 工作流 |
| [Gamer modeling](engine/reverie_gamer_modeling_pipeline.md) | Blender/Ashfox、模型工作区与导入流程 |

子项目的 [Python README](../ReverieCli-py/README.md)、[Desktop README](../ReverieCli-ui/README.md) 和 [Plugins README](../plugins/README.md) 保留各自安装/构建入口；第三方内置 Skill 文档、许可证和上游 changelog 不属于本次产品文档合并范围。

## 历史与迁移规则

原有 25 份分散的历史文件已完整迁入两份历史文档，`docs/` Markdown 数从 **44 减为 22**；其中另有一份原位于 Python 子项目的记忆审查记录。两份历史文档的目录列出每个原路径和新锚点，可按旧文件名定位。正文保留原测试数字、失败、平台限制与旧决策，仅调整层级和内部链接。

- 当前指南只描述已有行为；每个新功能规格明确标注“提案/实现中/已验收”。不要把计划写成能力。
- 新的日期化验证追加到 `VERIFICATION_HISTORY.md`；旧计划/交接追加到 `DEVELOPMENT_HISTORY.md`。原章节视为历史证据，不改写成新一次测试通过。
- 结构化证据继续保留在 `docs/verification/*.json`；它们是原始记录，不为减少文件数而合并或改写时间戳。
- `.runtime/`、`result_images/`、本地安装包和截图是本地材料，Git 克隆中可能没有；公开文档须独立说明测试条件与限制。
- 项目更新只进入 `changelog.md`；同一版本的多个更新放在同一版本下。没有 release 证据的工作进入 Unreleased；不凭 Git 提交日猜发布日，不填补不存在的版本。

本次整理的完整文件备份与 SHA-256 清单位于仓库内 `.runtime/docs-20261008/`，可恢复原来的未提交文档内容。该目录是本地可复核材料；公共导航与历史正文不依赖它才能阅读。

## 源码真源与检查

CLI 名称以 [help_catalog.py](../ReverieCli-py/reverie/cli/help_catalog.py) 为入口，执行能力还须核对 [commands.py](../ReverieCli-py/reverie/cli/commands.py) / [__main__.py](../ReverieCli-py/reverie/__main__.py)。Desktop 派发看 [App.tsx](../ReverieCli-ui/src/App.tsx)、[core-actions.ts](../ReverieCli-ui/electron/core-actions.ts) 和 [sdk_bridge.py](../ReverieCli-py/reverie/sdk_bridge.py)。存储位置看 [storage.py](../ReverieCli-py/reverie/storage.py) 与 [runtime-paths.ts](../ReverieCli-ui/electron/runtime-paths.ts)。

从仓库根运行 `python scripts/verification/check_docs.py` 检查本地文件/标题链接；检查不验证外部网址、自然语言事实或产品运行结果。
