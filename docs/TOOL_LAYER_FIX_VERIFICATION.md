# 内置工具延迟与活动日志修复验证

初始记录：2026-11-04；当前源码复核：2026-11-05（America/Denver）。

修复针对任务列表长时间等待、任务数据串项目、工具活动状态不结束，以及 API 连接日志被放入工具调用组的问题。最初基线为 `343ef970690e7c9e3b9895427d214de03497eb7c` 的工具执行器；开始工作时已有未提交的构建和只读任务快照修复，均予以保留。2026-11-04 用户限定仅提交对话页面布局：`273f0b92d2317ddcc2a0af190b7e49b55cd5f840` 当时已推送到 `origin/main`，只包含 `styles.css` 和布局回归测试，其余修复当时保留本地。2026-11-05 用户授权审查并发布其余源码，本次补充修复与当前验证见下文；未创建 GitHub Release。

最终按用户确认保留微信、钉钉式的左右聊天布局：用户消息和头像在右，Reverie 回答在左。仅将思考、活动日志和工具详情与左侧回答正文对齐，移除叠加缩进，统一分组间距。早期将所有消息左对齐的方案已撤回。

## 修复行为

- `task_manager` 的 `list`、`view`、`show`、`view_tasklist` 等查询别名跳过整仓库写操作快照。添加、更新任务继续保留工作区保护。
- 已知内置工具和别名直接查找，不触发 MCP、运行时插件或 RATS 的动态目录同步；动态工具仍通过原有同步流程发现。
- 按解析、规范化后的项目路径隔离任务存储。同一进程、同一项目的存活工具实例共享存储及锁，避免跨项目串数据，并保留当前存储生命周期内的任务 ID、描述和依赖。
- 查询和更新前检查固定任务文件的修改时间与大小，仅在外部变化时重新读取。普通查询不重写现有规范清单；同项目的不同实例能读取对方保存的变化。已清理的任务不会从旧缓存重新出现。
- 活动日志按连续事件的类别分组：API 连接、工具调用步骤、运行活动。分类保持事件顺序，API 活动不再计入工具组。
- 工具完成结果保留开始事件的工具名称、参数；结果省略 `status` 时，根据结果推导完成或失败状态。重放的开始事件不会覆盖已有结束状态。
- 折叠的工具日志延迟格式化参数、结果和详细文本，展开后再处理完整内容。

## 2026-11-05 审查、修复与当前验证

审查发现，直接改为每实例独立存储会使同项目新实例从纯 Markdown 重建任务，丢失内存中的 ID 和描述等元数据；并发刷新、修改和保存还可能覆盖另一实例的新增任务。此外，查询时新出现的旧格式文件可能触发迁移写入。三类问题均有失败回归复现，修复后通过：项目内共享存储和可重入锁覆盖刷新与完整操作，只读刷新使用 `load(migrate=False)`。

锁只协调同一进程内的任务工具，不提供跨进程文件锁。Markdown 导入仍有既有格式限制：外部编辑导致重载，或共享存储没有存活引用后重新建立时，不能保证恢复未落盘的丰富元数据。首次初始化对原有旧格式文件的迁移行为保留。本次没有重新设计持久化格式。

| 当前验证项目 | 结果 |
| --- | --- |
| Python 定向回归 | `python -m pytest ReverieCli-py/tests/test_task_tool_isolation.py ReverieCli-py/tests/test_read_only_tool_latency.py -q`：22 passed |
| Python 完整回归 | `python -m pytest ReverieCli-py/tests -vv --durations=10 -o faulthandler_timeout=90`：3180 passed，7 skipped，595.66 秒，退出码 0；可选真实 Engine/Cli 配对等跳过项不视为已验证 |
| 只读迁移变异检查 | 在独立进程将刷新改回允许迁移，两个旧格式只读测试均失败；未修改工作区源码 |
| UI 完整回归 | `npm test`：476 passed，1 skipped；包含 API 分组、参数保留和结果省略状态的交互检查 |
| 类型及生产构建 | `npm run typecheck`、`npm run build`、`npm run build:kernel` 和 Electron Windows 目录包构建通过 |
| Python 包 | `python -m pip wheel ./ReverieCli-py --no-deps` 隔离构建 Windows wheel 成功；解包核对任务存储、工具执行器与当前源码正文一致 |
| 当前目录包实际执行 | 新前端和新 PyInstaller 内核通过本地 HTTP SSE 服务执行 `task_manager(action="list")`，服务收到真实工具结果，随后回答正常完成 |
| 原生桌面界面 | Playwright 连接本次启动的隔离 Electron 窗口，检查 API 独立分组、工具停止转圈、展开参数及三个状态的结果；截图人工复核通过，未记录 renderer error |
| 只读落盘检查 | 3000 文件合成项目中，执行前后清单内容及 `mtime_ns` 相同 |

前端第一次运行因沙盒临时目录重命名 `EPERM` 而未执行测试；切换项目内临时目录后完整通过。Python 首次沙盒全量运行停顿后结束，改用项目内临时目录重新完整执行。测试日志中的既有 jsdom canvas 未实现提示、Git 换行提示和构建大 chunk 提示未被隐藏。

当前构建 ID 为 `0a501afd0934ba5d`。验证产物在 `.runtime/publication-review-20261105/`：

- `python-focused.log`、`python-mutation.log`、`python-full-final.log`、`ui-tests-final.log`：本轮回归记录。
- `ui-typecheck.log`、`ui-build.log`、`kernel-build.log`、`desktop-package.log`、`wheel-build.log`：本轮构建记录。
- `desktop-check/report.json`、`desktop-check/activity-expanded.png`、`desktop-check/completed.png`：当前包的实际工具执行与界面证据。
- `desktop-package/win-unpacked/ReverieUI.exe`：本次验证目录包，必须保留整个目录使用。
- `wheel/reverie_cli-2.5.3-py3-none-win_amd64.whl`：本轮 wheel，SHA-256 `af8c06771091a8a4c36829302b9c46e41582421b4983e9725ed4d638b3244ae6`。

本轮只访问本地合成模型服务，没有新增真实远端模型调用，也未更新已安装程序或上传二进制发行包。下文 2026-11-04 的真实模型测试、安装入口、构建 ID 和哈希属于历史版本，不作为当前最终源码的验证结果。

## `rce.md` 资源例外

`reverie/builtin_skills/reverse-skill/upstream/skills/pentest-tools/src-hunter/references/playbooks/rce.md` 是第三方安全分析 Skill 的 Markdown 参考文档，来自 `UPSTREAM.md` 记录的 reverse-skill 导入；包含命令注入、反序列化、Webshell、反弹 Shell 等攻击示例。它作为参考资源随 Skill 打包，不能仅凭扩展名认定内容无风险。

本机 Defender 将该资源标记为 `Trojan:Win32/Kepavll!rfn`。2026-11-05 读取的相关检测记录显示 `ActionSuccess=true`，威胁记录为 `IsActive=false`、`DidThreatExecute=false`，实时防护保持启用。这些字段说明相关检测的记录状态，不等于整机安全证明，也不能据此断定误报；未执行或恢复示例，未关闭防护或添加排除项。

当前工作区中的隔离删除继续保留，但不混入工具修复提交。原有 Git 历史及远端该文档未被移除，重新检出或复制时仍可能告警。本轮从现有工作区构建的目录包和 wheel 不包含该缺失资源，属于明确的资源例外。

## 2026-11-04 历史验收与验证

| 验收项目 | 验证结果 |
| --- | --- |
| 只读清单不扫描工作区，写入仍受保护 | 针对性测试通过；包含查询别名及写入快照检查 |
| 内置工具不等待动态目录 | 回归测试令动态同步直接抛错，内置清单查询仍成功 |
| 跨项目隔离、外部编辑、清理、同项目多实例 | 5 项新增任务工具回归测试通过 |
| API 与工具分组、计数、结果转圈结束 | React 实际交互测试及流式合并测试通过 |
| 对话排版 | 最终布局的真实 Chromium 检查 8 项通过，覆盖经典/玻璃、深色/浅色及宽/窄窗口，验证历史和即时用户气泡在右、回答在左；恢复左对齐错误的变异检查会触发失败；最终目录包的玻璃深色原生窗口已确认左右布局 |
| 广泛回归 | 前端 469 通过、1 跳过；Python 首次全量 2923 通过、7 跳过、1 超时失败 |
| 超时失败复核 | 未修改的 `test_riu_native_calibration.py` 在 500 ms 滚动稳定性等待超时；整个模块单独复跑 73 项全部通过，未修改测试或放宽阈值 |
| 类型检查和构建 | `npm run typecheck`、桌面前端构建、PyInstaller 内核构建、Electron Windows 目录包、NSIS 便携包构建通过 |
| 桌面实际执行 | 新目录包通过本地 HTTP SSE 服务执行清单工具，收到真实清单结果并完成回答；在原生窗口展开参数和结果检查通过 |
| 真实模型服务 | 已配置的 NVIDIA Step 5 Preview 成功调用实际工具，并准确报告三项清单状态 |
| 便携包启动 | 最终左右排版版在常用入口执行 `--tui --kernel-info`，退出码 0；直接内核兼容 JSON 有效，退出码 0；解压内核、`app.asar` 与最终目录包一致，详见 `chat-layout-installed-update.json` |

首次 Python 全量运行并非零失败；独立复跑通过支持该 500 ms 浏览器等待为短暂时序失败，不能据此宣称首次全量通过。

## 2026-11-04 历史本地工具耗时

同一台 Windows 机器、同一份含 3000 个源文件和 1 个任务清单的隔离工作区，各执行 5 次实际 `ToolExecutor.execute`。包括执行器日志、内存事件及原有快照开销，不包含模型和网络时间。测量时也有回归测试和构建进程运行；样本量小，不能推广为所有项目或工具的固定性能保证。

| 操作 | 基线中位数 | 修复后中位数 | 基线首次 | 修复后首次 |
| --- | ---: | ---: | ---: | ---: |
| 查询任务列表 | 905.651 ms | 1.187 ms | 31220.449 ms | 7.446 ms |
| 读取文件 | 29.058 ms | 32.256 ms | 52.377 ms | 26.572 ms |
| 列目录 | 39.937 ms | 34.474 ms | 38.828 ms | 34.828 ms |

显著改善集中在任务列表错误进入整仓库快照的路径；文件读取结果没有证明稳定加速。

## 2026-11-04 历史运行链路证据

桌面测试使用重新构建的目录包、独立配置与 3000 文件测试项目。HTTP SSE 服务故意在首次响应前等待 700 ms；从首次请求到服务收到工具结果共约 1055 ms。内核生命周期审计记录任务工具成功，工具阶段计时为 0 ms（整数毫秒精度）。原生窗口中确认了调用参数 `{"action":"list"}` 和三个状态的清单输出。

真实 NVIDIA 服务测试通过当前源码的完整 `ReverieAgent.process_message` 流程执行，使用已有 Step 5 Preview 配置和新建的合成工作区；没有发送用户项目文件。第一轮 API 连接约 7.3 s，工具开始至结果约 1.2 ms，整轮约 11.4 s，清单状态回答正确。该记录证明这一次真实调用成功，不能证明上游服务永远不会超时。目录包和便携包的集成执行使用本地 SSE 服务，两类证据分别记录。

## 2026-11-04 历史交付与记录

修复版沿用项目现有的 `2.5.3` 版本标记，内容已经重新构建：

- `dist/Reverie-Portable-2.5.3-x64.exe`：修复版 Windows 便携包。
- `.runtime/tool-layer-fix/chat-layout-package/win-unpacked/ReverieUI.exe`：包含本地工具修复与最终左右对话排版的目录包入口，必须与同目录运行时文件一起使用。
- `.runtime/tool-layer-fix/before/`：原便携包和修改前已有工具执行器、测试文件的备份。
- `.runtime/tool-layer-fix/tool-latency.json`：全部耗时样本。
- `.runtime/tool-layer-fix/python-tests.log`、`ui-tests.log`、`calibration-retest.log`、`layout-ui-tests.log`：回归记录。
- `.runtime/tool-layer-fix/real-provider-check.json`：真实 Step 5 Preview 运行记录。
- `.runtime/tool-layer-fix/desktop-check/`：本地 SSE 服务记录、工具结果和独立桌面配置。
- `.runtime/tool-layer-fix/chat-layout-installed-update.json`：最终左右排版版在常用入口的启动及解压文件一致性检查；此前的 `portable-smoke.json`、`layout-portable-smoke.json`、`left-column-portable-smoke.json` 仅属于相应旧版本。
- `.runtime/tool-layer-fix/chat-layout-result.jpg`：最终目录包原生窗口的左右对话排版截图，使用合成测试对话；对话文字是测试数据。
- `.runtime/tool-layer-fix/chat-layout-tests.log`、`chat-layout-mutation.log`：最终布局的正向及变异回归记录。
- `dist/reverie.exe`：重新构建并更新的独立单文件 CLI；`--version` 和 `--kernel-info` 均通过，原文件保存在 `before/reverie.exe`。

独立 CLI SHA-256：`d19522fe158a5143f5258e71ba116e4a16892c5204ab95a91c5c57d030d9c95c`。

最终桌面构建 ID：`2326109b66e4f805`。

便携包 SHA-256：`78ab814331420416bcf8e0e34b487f7ea49e90299c4dd9507627b15f86e2313b`。

便携启动烟测包括启动器等待及退出，不代表工具调用耗时。NSIS 启动器的 stdout 为空；兼容 JSON 由解压后的内核直接获取。最终包同步到 `D:/Program Files/Environment/Reverie/Reverie-Portable-x64.exe`，原有两个程序文件保存在 `.runtime/tool-layer-fix/installed-before/`；配置和会话数据保留。原生布局验证窗口及本地测试服务已关闭，效果截图和验证记录保留。

用户原有的未提交改动与已删除的上游技能文件未被清理或还原。安装在其他位置的程序不因源码变化自动更新，应使用此次重新构建的入口。
