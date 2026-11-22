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

## b293b7a 的只读来源复核

候选 `b293b7a46718a9373752672518d291bb476df5cc` 的六个 SDK / 桌面协议文件，与原清单的 Git blob 完全相同。109 个 Python 分派、102 个桌面请求/响应、110 个动作并集和 87 个导出类型仍是该候选的静态声明；它们不构成逐项运行验收。独立 GitHub API 核对了其源码树 `ceaa4f2359eae88c3760bb2c95a08316c104d6d0` 的 1566 个受管条目，与本地提交完全一致。

证据保存在已获准的 C 盘候选目录 `candidate-b293b7a/phase0A-source-identity.json` 和 `github-source-verified.json`。这里仍不冻结正式纯 Python 基线、查询题集或成绩，后续 CI 修复候选须继续对应其实际来源。

## 84e3c92 的只读来源及原生依赖复核

来源 `84e3c92c4c5a80e491e9da97b2e26735ece3a048` 的六个协议文件仍与清单 blob 相同。其 GitHub 源码树 `d228b3c17036b0a406f075b61e8ea5ae0154daf0` 的 1566 个受管条目，与本地提交的路径、模式、对象类型及 SHA 完全一致。静态动作数量和证据片段口径保持原记录的边界，正式基线及题集未冻结。

本轮从官方 crates 元数据再次取得 Bevy、两种物理适配器、底层 Rapier、FastEmbed 和 ort 的指定版本及许可声明；适配器底层依赖明确为 `=0.35.0-glamx0.2`。官方 E5 与 BGE 模型卡及配置固定到读取到的修订，E5 为 384 维，两者卡片均标 MIT。只读元数据不证明本地推理、通用 INT8 或四平台加载。

`ort-sys 2.0.0-rc.15` 实际源码包 SHA-256 为 `8d22b0417f1838db5a3ac0b3f98dfe39f6fb73624aa0a27c6bbb5040b9c7db2b`。其 `build/download/dist.tsv` 不含 `x86_64-apple-darwin`；不同 API 级别可配置，sys 默认 API 17，不能将其自动等同于最终 FastEmbed/ort 组合的 ABI。官方 ONNX Runtime 仓库及 release 入口本轮返回 404，[官方安装文档](https://onnxruntime.ai/docs/install/)可读取并列出官方包及源码构建方式。没有足够证据确定最终四平台原生版本及再分发材料，最小缺失证据是固定来源及版本的实际原生包、许可集和与所选 wrapper 的加载结果。

这些记录保存在 C 盘任务目录 `candidate-84e3c92/` 中的源码、依赖、模型及 ONNX 只读 JSON；首次 crates API 读取失败的记录也保留，带明确 User-Agent 的后续读取成功。未创建 Rust 工作区、构建这些依赖或加载模型。原生库交付策略的用户选择仍等待答复，不能改变四平台、本地 CPU 和性能门槛。

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

## 当前候选的二次来源核对与生命周期观察

2026-11-22 对候选 `34e4dcd572ec6aa086ba3cec78cc45856b4df04b` 再次只读核对。原清单所读的六个 SDK / 桌面协议文件与 `5725d07` 的 Git blob 完全相同，109 个 Python 分派、102 个桌面请求/响应、110 个动作并集和 87 个导出类型仍适用于当前候选。逐文件身份保存在 `.runtime/rust-3.0/phase0A/current-candidate-source-identity.json`；原草案不覆盖、不冒充正式冻结。

| 链路 | 已观察的源码行为 | 迁移验收仍需补齐 |
|---|---|---|
| JSONL 入口 | 启动先写 `ready` / protocol_version=1；输出锁保证单条消息完整；异常返回请求 ID 和 `error` | 编码、错误形状、并发流次序和旧客户端实际互通 |
| 后台分派 | 七个已列出的动作使用独立 daemon 线程，索引请求通过工作区锁合并 | Rust 调度、背压、取消及正常关闭；不由静态线程清点推断性能 |
| 流式归属 | `prompt.event` 带请求 ID，并合并当前 run identity 与事件字段 | 会话/任务/运行归属、乱序与恢复、交付不确定状态 |
| 项目与退出 | 工作区切换释放原 interface；Electron 关闭先发可选 stopPrompt，再发 shutdown 并结束 stdin，等待进程退出 | 正常关闭、EOF、异常中断、数据库与工具进程释放的实际证据 |
| 截图坐标 | 返回图像使用 `returned_image_pixels`，保留捕获边界、裁剪及缩放；输入前再检查身份、窗口边界、可见 DWM frame 与遮挡 | 四档实际 DPI、裁剪/缩小图点击拖拽、运行中缩放及旧图拒绝 |

窗口截图的 `_identity` 没有单独的 DPI 字段。真实 DPI 验证必须覆盖最大化窗口外框可能不变时的运行中缩放，确认旧观察是否失效；当前只有源码观察，不能据此宣称发生了实际坐标错误，也不能用模拟用例通过替代实机验证。

本轮本机 `rustc` / `cargo` 再次返回 1.96.0；没有创建 Rust 工作区。阶段 0B 的题集、耗时样本与质量门槛仍未冻结或计算。

## 忽略规则的历史合同差异

2026-11-22 补充实包检查发现：规则先重新纳入 `!目录/keep.py`，之后再忽略整个目录时，当前 pathspec/扫描逻辑仍保留 keep.py，Git `check-ignore --no-index -v` 则将它忽略。原混合版和当前候选的 `_should_ignore`、`_should_descend_ignored_directory`、两个规则加载方法 AST 完全相同，既有行为测试也允许忽略目录内指定文件重新纳入。

这项观察不证明 Python 恢复引入回归。目录级断言的失败报告保留，随后明确文件级排除、检索结果移除和无变更 revision 的六项实包检查单独通过。是否在 2.5.5 改为完整 Git 目录语义，或保留兼容并在 Rust 3.0 确定规则，已向用户提问，尚未决定。

正式阶段 0B 应冻结默认规则、Git/Reverie 规则优先级、目录排除、重新纳入、规则变化后的缓存失效及对应语料。不能在未决定合同前修改实现，或把失败断言改名为通过。
