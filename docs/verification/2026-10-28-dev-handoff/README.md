# 2026-10-28 dev 分支接续证据

用户明确授权将当前仓库改动提交推送到新的 `dev` 分支。此目录解决新会话无法访问旧沙箱 `.runtime/` 的交接问题。[接续说明](../../CONTINUE_RIU.md)与[可复制提示词](../../CONTINUE_RIU.md)是新会话入口。

- [goal.json](goal.json)：本轮可随 Git 克隆恢复的目标和未完成项；[交接前 goal](goal-before-handoff.json)保留旧状态与旧授权限制。
- [evidence-manifest.json](evidence-manifest.json)：复制来源、Git 内路径、大小与 SHA-256。复制文件的内容未改写；原 `.log` 扩展名改成 `.log.txt`，便于正常纳入版本控制。报告中的旧绝对路径/`.runtime` 路径仍是原执行环境的历史引用，不表示 Git 克隆包含那些完整目录。
- `evidence/`：保留的 v11/v12 构建与失败摘要、v12 原生富格式/P2/P3/P4/隔离、60 次压力、完整依赖 deb 隔离生命周期、探索性本地模型报告及四张主题/尺寸截图，以及 v12 后启动器重建失败的日志。
- [handoff-validation.json](handoff-validation.json)：本轮执行的检查、退出码和范围限制。
- [publication-manifest.json](publication-manifest.json)：本次将提交的变更文件内容校验表；清单自身排除，避免自引用。

最新源码包括保留 v12 **之后**的 Linux 已安装链接启动器修复。此前 v12 的通过记录仍有效于原包，不是这份后续修复的安装包验收。最后重建执行记录为退出137，末尾日志只到 deb target；原因未确立，新包尚未验收。

历史正式评估不重跑、不重评分；合成 UI 夹具与探索性 smoke 不增加正式模型接受样本。安装包、模型权重、依赖缓存和完整运行树未上传。原有 `docs/verification/` 证据 ZIP 与截图则按仓库当前内容保留在本次提交范围内。

首轮 GitHub 全新克隆内容校验通过，但发现两份文档引用的历史 v6 日志被 `*.log` 忽略；[失败检查](first-remote-clone-check.json)原样保留。修正提交将原始两份日志强制纳入 Git，不改日志内容；最终还需对修正后的远端进行干净克隆检查。
