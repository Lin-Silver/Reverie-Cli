# Rust Context Engine：本地语义链路与内核接入

完整范围仍按 [plan.md](plan.md) 实施，Python 2.5.5 保持冻结。以下步骤各自完成基本构建和实际运行检查后提交 `main`，不创建分支。正式质量、性能、完整平台与产品验收由 [UNVERIFIED.md](UNVERIFIED.md) 和 [云端提示词](CLOUD_VALIDATION_PROMPT.md) 承接。

1. 固定资源和本地推理：校验真实模型／tokenizer／ORT 字节，生产通用 INT8，运行原生模型探针并验证 CPU、向量维度和模型卸载。
2. 持久向量及混合检索：完成事务代际、增量复用、稳定排名、源身份检查、RRF、N=16 神经重排和历史预算；用实际小语料检查跨语言召回、重启、变更和删除。
3. 资源生命周期及共享内核：接入安装、校验、健康、原子激活、回退、取消和卸载；任务固定模型版本，加载／索引不占全局内核锁；用原生 SDK 验证实际资源和任务行为。
4. GUI／TUI 共用管理：显示资源、模型、索引进度和失败原因，管理入口调用相同 actions；验证真实 Electron 窗口和终端输入／取消。
5. 正式证据：四平台本地推理、完整量化质量、冻结 Recall／nDCG、预热延迟、内存、并发更新和恢复分别取得证据；基本通过不能写成完整 Context Engine 完成。

## 当前基本验证

2026-11-23：步骤 1 和步骤 2 首条可运行链通过本机基本检查，步骤 3／4 尚未接入。锁定 FastEmbed 7.7.1／ort 2.0.0-rc.15；完整 Rust 工作区 33 项通过，Clippy `-D warnings`、格式及锁定 release 构建通过。Windows EXE 32,794,624 字节，SHA-256 `69abbf84b9555a71df8d43e225bb95eb3048331e1d0dc00e9c4ef5723cdfd76d`。

真实通用 INT8 候选为 `.runtime/rust-3.0/semantic-resources/int8-gather-v2`，manifest SHA-256 `f87fd5c838935dfdb5ede89886d9896000aa76a4a9592d9cdb8553abeb3f7d91`；含 runtime 和许可资产共 449,946,508 字节。E5 为 118,308,811 字节，BGE 为 279,301,884 字节，原始 FP32 控制包为 1,635,063,911 字节。一次含加载的两向量／两候选探针为 2,337.55 ms，不能与预热 N=16 p95≤2 秒门槛混用。

`node scripts/verification/rust-semantic-smoke.mjs <executable> <real-bundle> <manifest-sha256>` 实际 7 项通过：持久向量、完整代际重启复用、无词法命中的跨语言语义召回、72 行与预算、旧正文拒绝、变更身份刷新、删除证据过滤。证据 `.runtime/rust-3.0/semantic-smoke/case-eX9A9o/report.json`，原始进程 stdout／stderr 同目录保存。移除未知 `user_version` 拒绝条件后定向测试 exit 101，原字节恢复后完整工作区通过，记录 `semantic-resources/storage-mutation.json`。

原生最近邻目前为精确余弦遍历加有限堆；完整 ANN、并发代际、资源激活及自动 Agent／GUI／TUI 语义接入尚未完成。INT8 和 FP32 完整质量比较、四平台推理及 Intel 同版本 ORT 源码仍为未验证项，不修改冻结题集或资源契约绕过问题。
