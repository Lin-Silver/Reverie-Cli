# Rust Context Engine：本地语义链路与内核接入

完整范围仍按 [plan.md](plan.md) 实施，Python 2.5.5 保持冻结。以下步骤各自完成基本构建和实际运行检查后提交 `main`，不创建分支。正式质量、性能、完整平台与产品验收由 [UNVERIFIED.md](UNVERIFIED.md) 和 [云端提示词](CLOUD_VALIDATION_PROMPT.md) 承接。

1. 固定资源和本地推理：校验真实模型／tokenizer／ORT 字节，生产通用 INT8，运行原生模型探针并验证 CPU、向量维度和模型卸载。
2. 持久向量及混合检索：完成事务代际、增量复用、稳定排名、源身份检查、RRF、N=16 神经重排和历史预算；用实际小语料检查跨语言召回、重启、变更和删除。
3. 资源生命周期及共享内核：接入安装、校验、健康、原子激活、回退、取消和卸载；任务固定模型版本，加载／索引不占全局内核锁；用原生 SDK 验证实际资源和任务行为。
4. GUI／TUI 共用管理：显示资源、模型、索引进度和失败原因，管理入口调用相同 actions；验证真实 Electron 窗口和终端输入／取消。
5. 正式证据：四平台本地推理、完整量化质量、冻结 Recall／nDCG、预热延迟、内存、并发更新和恢复分别取得证据；基本通过不能写成完整 Context Engine 完成。

## 当前基本验证

2026-11-23：步骤 1–4 的首条可运行链已经接入。共享内核增加资源安装、健康校验、原子激活、回退、卸载和受保护删除，索引和查询在后台执行；GUI 管理页和 `/context` 终端命令使用相同接口。当前 Rust 工作区 35 项、Clippy `-D warnings`、格式及锁定 release 构建通过。此前步骤 1／2 的 EXE 为 32,794,624 字节、SHA-256 `69abbf84b9555a71df8d43e225bb95eb3048331e1d0dc00e9c4ef5723cdfd76d`，仅作其原始证据身份；后续程序身份见 [实施记录](progress.md)。

真实通用 INT8 候选为 `.runtime/rust-3.0/semantic-resources/int8-gather-v2`，manifest SHA-256 `f87fd5c838935dfdb5ede89886d9896000aa76a4a9592d9cdb8553abeb3f7d91`；含 runtime 和许可资产共 449,946,508 字节。E5 为 118,308,811 字节，BGE 为 279,301,884 字节，原始 FP32 控制包为 1,635,063,911 字节。一次含加载的两向量／两候选探针为 2,337.55 ms，不能与预热 N=16 p95≤2 秒门槛混用。

`node scripts/verification/rust-semantic-smoke.mjs <executable> <real-bundle> <manifest-sha256>` 实际 7 项通过：持久向量、完整代际重启复用、无词法命中的跨语言语义召回、72 行与预算、旧正文拒绝、变更身份刷新、删除证据过滤。证据 `.runtime/rust-3.0/semantic-smoke/case-eX9A9o/report.json`，原始进程 stdout／stderr 同目录保存。移除未知 `user_version` 拒绝条件后定向测试 exit 101，原字节恢复后完整工作区通过，记录 `semantic-resources/storage-mutation.json`。

真实 SDK 10 项检查保存在 `.runtime/rust-3.0/semantic-sdk-smoke/case-lNDsQ3/report.json`：安装时执行模型探针并复核内容、验证期间仍能读取内核状态、实际混合查询和 Agent 证据、坏 ONNX 保留旧激活、取消保留旧代际、更新时原任务固定旧版本、回退、显式删除和重启接续。输入类型在操作登记前反序列化，字符串修订号被拒绝且激活原文不变。

原生最近邻已改为 USearch 2.26.6 的 HNSW／Cosine／F32 图，连接数 16、构建及查询扩展 128、有限候选扩展后稳定排序；默认 NumKong／OpenMP 关闭。图与向量同事务提交、附 SHA-256，常驻内核的 fork 共享已校验图。语义 schema 1 先一致性备份再迁移至 2，向量合同 1 和旧身份保持。自动语义追赶、完整并发／恢复和原生推理即时取消继续实施；完整质量、ANN 召回损失、四平台推理及 Intel 同版本 ORT 源码仍为未验证项。

本机 ANN 增量：工作区 37 项、Clippy、锁定 release 构建与原生入口 6 项通过。实际 Windows 程序为 33,777,664 字节、SHA-256 `93fab89c1d36303c613d9c9b487dd4167ef8bbfa464dea1a6b3ca8f03d896918`，真实 E5／BGE 7 项报告在 `.runtime/rust-3.0/ann-smoke/case-0Vpl3y/report.json`。新增数据库用例验证 schema 1 的取消、备份恢复、旧向量／证据身份保留、图缓存复用、损坏拒绝和重建；这不是完整性能或四平台验收。

原生后台监听已接入同一内核：notify 文件事件按 Git 忽略目录发现监听范围，结构索引先提交，语义代际随后追赶。暂停使用持久 `auto_index` 设置，取消绑定项目和操作 ID，关闭释放线程及原生监听句柄。自动事件不复用已结束请求 ID；资源激活后唤醒相关监听，正在运行的操作仍持有原资源。语义库版本不兼容时保留该数据库并继续提供基础证据。

本机工作区 38 项、格式、Clippy `-D warnings`、锁定 release 构建、桌面类型与翻译、生成协议一致性、生产构建、桌面桥接定向 12 项和实际 PTY 9 项通过。实际 Windows E5/BGE/HNSW 监听检查 6 项通过，报告 `.runtime/rust-3.0/context-watch-smoke/case-3nFdmA/report.json`；PTY 报告 `.runtime/rust-3.0/tui-smoke/case-QTYuUt/report.json`。这些结果仅证明对应基本行为，完整平台、网络文件系统、性能、质量和并发仍在未验证清单中。

实际 Electron 窗口第二次 9 项通过，报告 `.runtime/rust-3.0/electron-watch-smoke/case-GG0L3v/report.json`，界面截图已检查。首次 `case-5kW1Xf` 在探针 20 秒内未观察到安装完成；之后同一程序对同一工作区通过 SDK 安装用了 6.21 秒，第二次窗口通过，尚不足以确定首次原因。原日志与截图保留，探针补充实际 Context IPC 参数和失败记录，问题继续列为未验证。该增量 Windows EXE 为 34,235,392 字节，SHA-256 `3957ece0024d226afde27942ae7e49b4196b60305b8c92626dfecc5033ee57ee`。
