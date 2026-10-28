# 给新 Codex Cloud 会话的接续提示词

继续完成 Reverie CLI / Desktop 的 RIU 任务。请实际执行、自主推进，直到全部已授权且可执行的工作完成；不要只给计划或用局部通过宣称整体完成。

仓库：https://github.com/Lin-Silver/Reverie-Cli.git
继续分支：`dev`。这是 2026-10-28 将旧会话当前改动保存到 GitHub 的接续分支，版本仍为 2.5.0。

若工作区为空，在新目录运行：

```sh
git clone --branch dev --single-branch https://github.com/Lin-Silver/Reverie-Cli.git
cd Reverie-Cli
git branch --show-current
git log -1 --format='%H %s'
git status --short
```

此快照基于 `350c5ba`；核对时远程 main 为 `80fad92`，另有4个提交，未混入本次工作区快照。后续整合时先审查差异并保留两侧工作。

若已有 checkout，先核对路径、remote、分支和未提交改动；保留用户工作，不要覆盖已有目录、强制切换或回退。先读取根目录 `AGENTS.md`、`docs/CONTINUE_RIU.md`、`docs/verification/2026-10-28-dev-handoff/goal.json`、`docs/RIU_COMPLETION_PLAN.md`、`docs/ROADMAP.md`、`docs/FEATURE_STATUS.md`、`docs/RICH_ANSWER_UI.md` 与本轮证据索引。新的 Git 克隆有源码、测试、文档、关键报告和已有文档证据归档，不依赖失败的 ZIP 下载；没有完整 `.runtime/`、旧 v11/v12 安装包或本地权重是预期情况，按源码重建，不要求提供旧沙箱。

主目标是参考图里的富格式回答 UI/UX：统计卡片、项目总览表、状态徽标、图片推荐、编号/来源胶囊/可点击链接、中文排版、深浅主题和响应式效果。交互视图及其生命周期仍要有，但路线规划不是重点。用户已取消 200k 上下文设置，不要更改。

保留的 v12 Linux build `fcce0356b0365178` 已通过 AppImage FUSE 富格式86/86、P2 24/24、提取程序P3/P4/隔离26/31/36，60次合成P4 31/31；deb无强制跳过依赖的Bubblewrap隔离安装→升级→卸载通过。历史Python全量2392通过/24跳过，Renderer425通过/1跳过。一次Qwen3.5-4B应用内合成smoke耗时118.47秒并准确显示指定内容；它是探索性证据，正式接受样本0，不能代表广泛模型质量。

立即优先处理：当前源码在v12之后又修复了Linux安装链接启动器，源码/回归测试已存在，但包含此修复的新安装包尚未通过构建和启动验收。保留的v12结果不能覆盖这份后续修改。旧重建最后记录退出137，原始日志仅表明进入deb target，根因未确立。检查可用磁盘、网络代理、Python/Node依赖和显示环境，在独立目录重建正确源码，核对Pillow、权限、启动器与构建身份，测试真实安装链接、带空格项目目录和参数传递，再完成必要原生验证。

其他开放项：Windows x64/macOS arm64/x64真实系统安装运行、Linux宿主系统安装及已安装桌面启动、物理IME/屏幕阅读器/设备输入、小时级稳定性，以及未达标的正式模型质量。环境不具备的事项保留精确阻塞，继续所有独立工作，不伪造通过。正式两组模型评估已关闭：不得第三组、选择性重跑或重评分历史；合成夹具与探索性小模型smoke均计0正式接受样本。最初LFM/MiniCPM公开免费API搜索记录已在文档中，先读现有结论，避免反复无效检索。

继续保留执行器、审批、会话锁、沙箱、私有状态、原生思考和普通工具路径。禁止覆盖历史报告、失败、安装包、已有release/.kernel/Python构建目录；新证据用唯一新路径。不要新建API Key、付费、升级版本或发布；后续commit/push需要新的明确授权，本次2026-10-28授权只用于保存当时快照。同步维护完成清单、路线图、功能状态、验证历史、changelog与持久化goal，分清历史包、当前源码、本轮实测和外部阻塞。先简要报告实际恢复状态和下一步，然后执行。
