# 阶段 0A：候选来源的只读清单与语料草案

本记录对应候选提交 `5725d076999a64a13f3d80b4235dc2d39b122022`，日期为 2026-11-22。该提交仍在 `codex/python-2.5.5-pure`；正式纯 Python 2.5.5 尚未重发，Rust 实现尚未开始。这里的清单、源代码锚点和依赖元数据不构成功能、性能或完整产品验收，也不提前冻结正式题集。

## 来源与静态观察

清单从 `git show <候选 SHA>:<路径>` 读取提交快照；Python 源码只经过 AST 分析，没有导入或执行其中的模块。未读取用户配置、凭据、会话、原稿、真实模型输出或私人游戏资产。

| 清单 | 本轮已观察内容 | 尚缺证据 |
|---|---|---|
| SDK / 桌面桥接 | Python 分派 109 项；桌面请求与响应声明各 102 项；动作并集 110 项；87 个 TypeScript 导出类型 | 每个动作的真实输入/输出、委托校验、流式次序、取消及关闭恢复 |
| 客户端组件 | 14 个 Python 来源文件、41 个类声明，含 RAT/RATS/RTP、插件、视图、流式协议、解析、移交和小说记忆 | 动态 schema、错误与重试语义、旧客户端和实际服务互通 |
| Gamer 声明 | 23 个类型、`2D` / `2.5D` / `3D` 三种维度，形成 69 行组合草案 | 适用性须在验收前确认；运行、完整作品与独立导出均待验证 |
| 检索草案 | 26 条查询和 26 个公开源码/文档来源，含一个短小说记忆夹具 | 最小相关片段裁定、负例、正式公开许可小说和游戏资源、独立难例及冷/热基线 |

Python 分派与桌面类型声明存在以下差异：

| 动作 | Python 分派 | 桌面类型声明 | 当前观察 |
|---|---|---|---|
| `hello` / `shutdown` | 有 | 无 | 内核握手与关闭入口；迁移清单必须记录其生命周期 |
| `releaseView` | 无 | 有 | Electron `main.ts` 在宿主内处理，并可停止绑定视图的执行任务；不是缺失的 Python 分派 |
| `callPluginTool` / `getRecovery` / `inspectPlugin` / `listSessions` / `listSettings` / `resolveComputerImage` | 有 | 无 | 需补齐调用来源、别名和类型映射，不将静态缺口直接判为运行失败 |

`callViewTool`、`compactContext`、`indexWorkspace`、`resumePrompt`、`runPrompt`、`workspaceMentions`、`wstyleCommand` 进入现有后台分派清单。后续逐项核对请求归属、会话隔离、审批等待、停止、交付不确定状态和退出清理，不能只验证返回类型。

现有 `UserInputTool` / `ask_user` 的参数是问题、原因、多行、默认值和取消选项，源码通过 `console.input()` 读取。所读文件没有结构化选项数组及 GUI 问题答复合同；实际 SDK 行为仍待逐项验证。Rust 的共用询问流程按完整计划提供 1–3 个选项及自定义回答，绑定任务，明确提交，并与 `resolveApproval` 的权限答复分开处理。

## 证据片段口径与题集边界

用户已于 2026-11-22 确认 Recall@10 按证据片段评价。片段身份绑定语料版本、文件、位置和内容摘要。正式冻结时必须固定最小相关范围、返回上限、总预算及去重规则；完整预标注证据及版本匹配才算命中。

当前查询草案的类、函数和文档标题锚点已确认存在且唯一；整段声明的范围不是最终相关片段。查询覆盖精确定位、裁剪缩放坐标、遮挡与旧图拒绝、索引事务、重命名/删除、旧索引备份、长对话移交、安全重试、插件布尔值、小说连续性、游戏范围及存档等链路。短小说夹具仅用于验证公开数据形状，不替代正式叙事语料或文学验收。

阶段 0B 再冻结原始语料、查询分组、中英及跨语言标签、最小相关片段、负例与难例。公开的开发查询不冒充独立验收难例；先测最终纯 Python 基线，保留 Recall@10 增加 10 个百分点及原有性能门槛。基线超过 90% 时先报告数学上限，再由用户决定目标形式。

## 依赖与许可：事实、声明及未验证项

| 项目 | 本轮已验证事实 | 实际集成状态 |
|---|---|---|
| Rust / Cargo | 本机命令均返回 `1.96.0` | 未创建 Reverie Rust 工作区 |
| Bevy | 上游 `v0.19.0` 清单为 Edition 2024、MSRV `1.95.0`、`MIT OR Apache-2.0` | 未编译或运行 |
| `bevy_rapier2d` | 上游 `v0.36.0` 清单声明 Apache-2.0、Bevy `0.19.0`；workspace 固定 `rapier2d/3d =0.35.0-glamx0.2` | 不将适配器版本与底层 Rapier 同名版本混为一谈；新栈未集成 |
| FastEmbed | crates.io `7.7.1`，未撤回，Apache-2.0，MSRV `1.88`；仓库来自官方元数据，为 `Anush008/fastembed-rs` | 未安装 crate 或执行推理 |
| `ort` | crates.io `2.0.0-rc.15`，未撤回，`MIT OR Apache-2.0`，MSRV `1.92` | wrapper 许可不替代原生 ONNX Runtime 及第三方材料 |
| E5 | 官方修订 `614241f622f53c4eeff9890bdc4f31cfecc418b3`；模型卡 MIT，配置 hidden size 384 | 未下载权重；量化、CPU 延迟及四平台载入未验证 |
| BGE reranker | 官方修订 `2cfc18c9415c912f9d8155881c133215df768a70`；模型卡 MIT | 未下载权重；重排和通用 INT8 质量未验证 |

参考实现仍固定到完整计划中的 Codex 和 ZCode 修订。本轮再次读取 Codex `NOTICE`，其中保留 Ratatui 的 MIT 派生署名；ZCode `NOTICE.md` 将第一方 Apache-2.0 与独立第三方条件分开。这里只读取声明，没有复制其实现、品牌或素材。后续复用按实际文件核对 LICENSE、NOTICE、第三方条目和修改标识。

FastEmbed `v7.7.1` 的 [Cargo features](https://github.com/anush008/fastembed-rs/blob/v7.7.1/Cargo.toml)（Git blob `697588ff35ea7e553226d7d7644ad7613e7873ed`）默认包含 HF Hub、ORT 二进制下载和 image models。Rust 集成阶段须按已锁定的轻量、离线资源方案选择必要 features，不能直接将上游默认下载和不需要的模型依赖带入客户端。这是构建方案要求，本轮没有执行依赖安装或推理。

主要来源：[Bevy 清单](https://github.com/bevyengine/bevy/blob/v0.19.0/Cargo.toml)、[Rapier 适配器](https://github.com/dimforge/bevy_rapier/blob/v0.36.0/bevy_rapier2d/Cargo.toml)、[适配器底层固定版本](https://github.com/dimforge/bevy_rapier/blob/v0.36.0/Cargo.toml)、[FastEmbed 元数据](https://crates.io/api/v1/crates/fastembed/7.7.1)、[ort 元数据](https://crates.io/api/v1/crates/ort/2.0.0-rc.15)、[E5 模型卡](https://huggingface.co/intfloat/multilingual-e5-small/blob/614241f622f53c4eeff9890bdc4f31cfecc418b3/README.md)、[BGE 模型卡](https://huggingface.co/BAAI/bge-reranker-base/blob/2cfc18c9415c912f9d8155881c133215df768a70/README.md)。

本机只读硬件核对为 Ryzen 5 5600X、6 核 12 线程、约 24 GiB 内存，符合已选参考机。没有据此取得任何性能成绩；模型、CPU/GPU 回退、通用 INT8、四平台原生推理和最小运行库仍需正式验证。

## 本地证据位置与后续检查

原始清单及脚本位于项目内 `.runtime/rust-3.0/phase0A/`：`sdk-protocol-inventory.json`、`component-protocol-inventory.json`、`gamer-type-matrix-draft.json`、`queries-draft.json`、`corpus-sources-draft.json`、`upstream/resource-metadata-audit.json`。这些本地派生文件不是 GitHub 发布资产。

下一步先完成阶段 P 的实际候选程序核对、四档真实单屏 DPI 和纯 Python 重发。正式来源明确后再冻结阶段 0B，测冷启动及预热各至少 30 次的耗时分解、质量和轻量基线，并逐项补齐协议运行合同。完整 Rust 范围、Gamer / Live2D 独立组件、全部 GUI/TUI 和市场流程及发布门槛继续以 [完整计划](plan.md) 为准。
