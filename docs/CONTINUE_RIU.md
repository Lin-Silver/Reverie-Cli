# RIU GitHub dev 接续说明

2026-10-28：用户明确授权把当前仓库全部源码、测试和文档改动提交并推送到新的 `dev` 分支。仓库为 `https://github.com/Lin-Silver/Reverie-Cli.git`。本次不升级版本、不发布 Release、不合并到 `main`。此前的“禁止提交/推送”限制对这次快照已由用户最新指令解除；其他限制继续适用。

## 从 GitHub 恢复工作

在新的空目录中运行：

```sh
git clone --branch dev --single-branch https://github.com/Lin-Silver/Reverie-Cli.git
cd Reverie-Cli
git branch --show-current
git log -1 --format='%H %s'
git status --short
```

本地快照基线为 `350c5baaed1b41f399ca09e01b912a4f81eaa80e`。核对时远程 `main` 为 `80fad92af9f7ce80384768b5897f6c4c99af4747`，比该基线多4个提交；本次 `dev` 保存当前工作区，不把这些独立远端改动静默合并进历史验收源码。后续如需整合 `main`，先审查差异并保留两侧工作，整合后重新验证。

如果 Codex Cloud 已经检出了此仓库，先检查工作区状态、远程和分支，保留现有改动；不要覆盖已有 checkout。确认 GitHub 远端 `dev` 后再安全切换或另建目录。实际推送结果与提交 SHA 由交付消息给出，不把尚未完成的推送写成已成功。

先读根目录 [AGENTS.md](../AGENTS.md)、[本轮持久化 goal](verification/2026-10-28-dev-handoff/goal.json)、[RIU 完成计划](RIU_COMPLETION_PLAN.md)、[路线图](ROADMAP.md)、[功能状态](FEATURE_STATUS.md)、[富格式契约](RICH_ANSWER_UI.md)和[原始证据索引](verification/2026-10-28-dev-handoff/README.md)。后续会话按本文的目标、证据边界和验证入口继续；独立 Cloud 提示词文件已移除。

Git 克隆包含现有全部非忽略源码/测试/文档改动、已有文档证据 ZIP/截图，以及本轮从 `.runtime/` 复制的关键报告、失败日志和 goal。它不包含本地依赖、旧 `.runtime/` 全树、v11/v12 安装包、3.8GB 模型权重、llama.cpp 二进制或 Xvfb 安装树。它们仍留在原环境；没有被删除。新环境中缺少这些材料时，应按现有源码和受支持脚本重新构建，不把本地路径、旧 sandbox 链接或旧包哈希当作可下载资产。

## 原始目标与优先级

最初任务包含寻找真正公开、免费的 Hugging Face 小模型 API，例如 LFM 或 MiniCPM。后来用户明确：重点是参考截图中的回答 UI/UX 和格式样式，包括统计卡片、项目总览表、状态标签、带图片的编号推荐、来源胶囊、可点击链接、深浅主题、中文排版与窄屏。交互式表单、图表、表格和视图生命周期也需要，但路线规划不是主线。

最终目标包括：可靠生成和展示这些回答，保留流式/追问/恢复行为、执行与隐私边界，提供有证据的性能和三端安装运行。用户取消了 200k 上下文设置。继续自主处理所有已授权可执行事项；遇到真实环境阻塞时继续其他工作并保留未完成状态。

## 已完成及证据边界

- 已实现富格式解析/渲染、参考图风格卡片和表格、推荐图片/徽标/来源/链接、深浅主题、宽窄布局、流式与会话恢复；自包含静态展示请求使用紧凑 Desktop 路线，普通工具请求保留原路径。
- 最后一次历史 Python 全量为 **2392 passed / 24 skipped / 14 warnings**；Renderer 为 **425 passed / 1 skipped**。这是原日期与源码范围的记录；本轮重跑内容单独写入本轮验证报告，不把历史结果当作新运行。
- 修复打包 Python 缺少 Pillow `_imaging`。保留的 Linux x64 v12 build `fcce0356b0365178`：FUSE AppImage 富格式 **86/86**、P2 **24/24**；提取程序 P3 **26/26**、P4 **31/31**、隔离 **36/36**；额外 60 次合成 P4 **31/31**，注册/输入 P95 **286.16/47ms**。
- v12 deb 在 rootless Bubblewrap 隔离根中，使用当前 Debian 13 依赖清单、无 `--force-depends` 完成 v11 安装 → v12 升级 → 卸载。宿主包数据库未修改，未完成宿主级安装及已安装桌面启动。
- v12 Qwen3.5-4B 应用内一次合成展示请求耗时 **118.47s**，四指标、两表行、编号卡与徽标/来源/链接匹配，深浅主题 × 1280/460px containment **4/4**、浏览器错误 **0**。这是探索性 smoke，正式接受样本仍为 **0**。
- 正式两组模型验收已经封闭。第二组 60 个位置中 59 份完成、1 份中断；原自动 31 项合格，4 项人工否定，其余 27 项不等于完整人工通过。不得第三组或重评历史。
- 免费接口搜索已留档：MiniCPM5-2B 官方 Space 曾匿名成功一次，但无 `tools/tool_choice`；MiniCPM-V 4.6 当前标准接口要求 Key；LFM 没有自有托管推理 API。见 [接口记录](verification/2026-10-20-riu-cloud/free-api-search.md)。

## 首要剩余修复：Linux 已安装启动器

v12 验收之后，发现 `/usr/bin/reverieui` 通过安装链接启动时，旧脚本按链接所在目录寻找 GUI。当前源码 `ReverieCli-ui/build/launchers/reverieui` 已解析真实脚本位置；已有回归测试验证安装链接、带空格项目目录和参数转交。

这份修复**尚未完成打包验收**。后续 deb 重建经历网络失败，最后一次日志停在进入 deb target，先前执行记录为退出 **137**；没有完成产物、内存诊断或根因证据，不能把 137 自动判为已确认 OOM。原始 v11、v12 首次构建 OOM、有效 v12 的早期 exit1、成功干净重试，以及本次启动器重建失败均继续保留。

下一步应在有足够空间的新环境，从这次 `dev` 源码创建独立构建目录，确认启动器、Pillow 和载荷权限进入同一新包；检验真实安装链接启动、CLI/GUI 参数和项目目录传递，再跑与改动相关的原生验收。先检查环境，遵守代理和凭据配置，使用仓库受支持脚本；不要复用会覆盖历史产物的输出路径。

## 其他未关闭事项

1. Windows x64、macOS arm64/x64 真实系统安装与运行。仓库有手动触发、只读权限且无发布任务的 `verify-riu-packages.yml`；构建或协议探针不能代替真实主机安装及用户操作。
2. Linux 宿主包数据库安装、升级、卸载及桌面启动。隔离生命周期已经通过，但不代替宿主实测。
3. 物理 IME、屏幕阅读器、焦点、真实设备尺寸/输入，以及小时级或更长稳定性。60 次合成循环不足以关闭这些门槛。
4. 正式模型质量未达标，历史失败保留。两组上限继续生效；只做已授权且与正式验收分离的探索性 smoke，不把合成夹具或一次小模型成功升级为广泛可靠性结论。
5. 每次实质修复后同步路线图、完成清单、功能状态、验证历史、changelog 与 goal，说明实现、已验收和环境阻塞。

## 验证入口

本次推送前的检查记录见 [handoff-validation.json](verification/2026-10-28-dev-handoff/handoff-validation.json)。已有依赖时，从仓库根可运行：

```sh
node --test ReverieCli-ui/scripts/package-validation.node-test.mjs
sh -n ReverieCli-ui/build/launchers/reverieui
python scripts/verification/check_docs.py
git diff --check
```

Renderer 测试与类型检查在 `ReverieCli-ui` 运行 `npm test`、`npm run typecheck`。Python 回归在 `ReverieCli-py` 使用已安装项目依赖的 Python 运行 `python -m pytest`；不要把缺失 pytest 或 Xvfb 的失败算作功能通过。新环境需要先检查 Python、Node、依赖、磁盘与可用显示环境，再选择安装或重用依赖。
