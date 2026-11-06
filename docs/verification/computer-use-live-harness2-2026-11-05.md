# Computer Use 实机与 Harness² 补充验收（2026-11-05）

本记录补充并更新同日早期的 Computer Use 交付记录。普通桌面路径仍为无障碍树 → ref → 语义操作 → 属性或条件验证，截图和物理输入是显式能力。没有提交、推送或发布 GitHub 内容。

## 实际桌面结果

| 项目 | 结果 | 证据目录（仓库相对路径） |
|---|---|---|
| 受控应用语义流程 | 52 项检查通过，语义阶段图片传输为 0 | `.runtime/computer-use-20261105-164412/` |
| 真实模型的无图片语义流程 | NVIDIA Step 5 Preview，Reverie 模式；find → set_value 中文 → get 验证，4 次模型请求，未传图片 | `.runtime/computer-model-20261105-170123-6265d3/` |
| 实际物理操作 | 16 项检查通过 | `.runtime/computer-physical-20261105-172033/` |
| 记事本 | 打开指定测试文件、无障碍观察、截图和关闭通过 | `.runtime/computer-apps-20261105-172332/` |
| 资源管理器 | 修复后能打开指定目录、观察完整树和截图；通过具体关闭控件清理测试窗口 | 同上 |
| Chromium | 页面标题可观察，指定编辑框查询和条件等待均未找到目标；本轮未通过 | 同上，`chromium-failed-snapshot.json` |
| 真实视觉模型 | 收到截图，但后续 API 请求超时；独立读取画布计数为 0，未通过 | `.runtime/computer-model-20261105-171454-1f26e1/` |

物理检查验证了实际状态：ref 点击和图片坐标点击各增加一次计数；验证条件超时后计数没有再次增加；焦点、Ctrl+A 和中文多行物理输入有属性回读；对角拖动令画布计数变为 1；scroll_to 与滚动可以调用；窗口位置、大小、最小化、最大化和恢复均有窗口库存回读，移动后的旧截图被拒绝。重复 AutomationId 和名称返回两个独立引用；此处的检查不证明这两个引用可安全操作，仍须遵守上游身份确认规则。

滚动检查的范围是目标可见状态和调用交付，未测滚动像素距离。真实视觉任务的完整推理闭环、正在交付的物理动作取消、开始菜单/托盘、多显示器及其他 DPI 尚未通过本轮实机验收。

Step 5 本身支持视觉。核对脚本发现早期 `--text` 只修改临时 ModelConfig，NVIDIA source 的 active_model 会重新生成，因而旧记录中的 `vision=false` 不等于工具上下文真的关闭视觉。4 次请求均无图片的事实已验证；不能将该样本当作真实纯文本模型能力门禁验收。脚本现将能力覆盖落实到隔离模型配置，并断言 effective_vision；该修正后尚未重跑桌面模型任务。文本模型媒体/坐标门禁已有回归覆盖，真实纯文本模型验收仍待补充。

最后一次调用独立 Computer Use 插件检查 Chromium 时，插件报告无法可靠确定当前浏览器 URL，因策略检查终止本轮桌面控制。此后未再通过其他界面入口绕过该限制。本次的 Chromium 快照表明窗口树可以完整遍历，但渲染编辑框未暴露；不足以确定 Chrome 的原生 provider 和上游遍历哪一层造成缺失。不能把 `complete=true` 当作所有可见控件均已暴露的证明。

语义 find 的 8 个本机样本 p50 为 250 ms、p95 为 266 ms，初始树约 14,403 个 JSON 字符。与旧样本的机器负载不同，不能据此宣称速度提升。

## 根据复现问题完成的改进

1. 文件夹目标通过 ShellExecute 打开。上游原生 launch 默认连接已运行进程并忽略新参数；带参数的原生启动现使用 `--no-attach`，已运行目标明确拒绝。启动交付仍与窗口出现分别报告。修复后的资源管理器实机检查通过。
2. 明确只允许 file_ops 读取的用户请求，首次请求要求原生 file_ops 工具调用；任何工具尝试后解除要求，包括失败尝试，避免重放。该用户回合只提供 file_ops schema；新的普通回合恢复常规工具列表。多工具范围、禁止读取、写操作和不可用 schema 不进入这个规则。
3. 已知 window_id 的初始观察、可选 root 和原生 role 的工具说明更明确，减少模型填写项目名、`None`、虚构 root 或 UIA 类名。GLM 的实测仍失败，未宣称该说明已让所有模型通过。
4. 校准工具与轻量 schema 宿主复用边界保持兼容。首次全仓回归发现两个 AttributeError，已通过 callable 方法检测修复，并重跑原失败项。
5. 实机脚本保留阶段、交付和独立效果证据，失败时返回非零；视觉任务在超时后仍记录实际画布计数。Harness² 使用 UTF-8 文件读写、真实跨进程 Windows 文件锁、POSIX tree key 兼容、无代理的本地记录器、整体校验后才应用模型编辑，子进程不继承提供方凭据。

同一 Step 5 合成任务，优化前首次成功 API 请求提供 56 个工具，prompt tokens 为 38,994；明确范围后的请求提供 1 个工具，prompt tokens 为 18,833，减少约 51.7%。这是单个请求体积的实测，不能外推任务质量或所有模型的性能。首次工具选择修复后确实出现原生读取；后续真实模型仍有错误、空最终内容、超时和限流。

## Google Harness²

官方来源：[google-research/harness2](https://github.com/google-research/harness2)，固定提交 `6868817518876de8fd170c6a8354daca273b6191`。上游 checkout 保持未修改。Harness² 是递归 harness 优化框架，正式适配的测评包括 JobBench、LAB 和 WorkBuddy-Bench。

| 层次 | 实际结果 |
|---|---|
| 上游 demo + Windows 兼容 bootstrap | 2 个任务完成、0 失败；两种递归模式运行，包含真实 Python 执行 |
| Reverie 当前内核 + 确定性模型服务 | 两个合成任务、两种模式，共 14 次真实 CLI 执行和 28 次 HTTP 请求全部通过；生成 4 条经验记录 |
| Step 5 真实求解与编辑 | 记录了从普通文本假调用到原生读取的对照；递归编辑多次没有最终 content，不能把 reasoning_content 当作有效交付 |
| GPT-OSS 20B 真实运行 | 提供方超时，未完成 |
| MiniMax M3.1 Flash 第一次运行 | base/invariant/domain/compose 共 4 次求解执行均通过；最后改进请求超过 65 秒，整轮未完成 |
| MiniMax 延长期限后重跑 | 请求期限 180 秒、CLI 420 秒，均限于隔离评测；遇到提供方 429，两次执行通过、两次执行未完成；整轮仍失败 |
| 官方 JobBench/LAB/WorkBuddy 分数 | **未运行，分数为 null** |

确定性服务运行验证真实 CLI、工具调用、输出、未修改输入、递归选择和经验继承，不是模型质量评测。真实模型失败报告全部保留；没有删除失败样本、将部分成功包装为整轮成功，或声称经验继承提升了任务得分。

官方要求 Linux、Python 3.12、安装具体 benchmark 的任务及依赖，并配置 solver/improver/judge。当前 Windows 没有可用 WSL/Docker；JobBench check 报告 9 个依赖或配置缺项，包括任务集、OpenCode 和 JobBench checkout/patch、document/judge 依赖及 judge 配置。没有通过安装系统组件、改写 judge 或使用合成任务替代正式分数。

证据目录：

- `.runtime/computer-harness2-demo-windows-verified/`
- `.runtime/computer-harness2-reverie-fixture-delivery/`
- `.runtime/computer-harness2-reverie-live-baseline/`
- `.runtime/computer-harness2-reverie-live-refined/`
- `.runtime/computer-harness2-reverie-live-final/`
- `.runtime/computer-harness2-reverie-gptoss/`
- `.runtime/computer-harness2-reverie-minimax/`
- `.runtime/computer-harness2-reverie-minimax-final/`
- `.runtime/computer-harness2-jobbench-check.log`

可复现的隔离命令示例：

```powershell
python scripts/verification/computer_use_smoke.py
python scripts/verification/computer_use_physical.py
python scripts/verification/computer_use_model.py source:nvidia reverie --text
python scripts/verification/computer_use_model.py source:nvidia computer-controller --vision --canvas --api-timeout=180
.runtime/computer-harness2-venv/Scripts/python.exe scripts/verification/harness2_reverie.py --harness2-source .runtime/computer-harness2-upstream --output .runtime/fresh-harness2-run --provider configured --model source:nvidia --nvidia-model minimaxai/minimax-m3.1-flash --max-tasks 2 --max-requests 48 --mode sequential --cli-exe ReverieCli-ui/.kernel/reverie/reverie.exe
```

输出目录必须新建；真实模型仍受提供方可用性和限流影响。桌面测试应在受控交互桌面运行，测试窗口必须取得前台，且不得绕过 Computer Use 插件的停止或策略限制。

## 回归与构建

最终全仓 Python 回归 **3,157 passed / 7 skipped**（611.41 秒），记录在 `.runtime/computer-full-delivery-python.log`。此前两个 schema 宿主失败已修复，最终全仓重跑没有失败。相关宿主/思考工具/模型请求回归另有 190 项通过；Computer/Harness² 定向回归 161 项通过。

UI 回归 **476 passed / 1 skipped**，记录在 `.runtime/computer-full-final-ui.log`。i18n、TypeScript、Vite 和 Electron 主进程构建通过。最终内核嵌入的 16 个相关模块字节码与当前源码相符；三处包内原生引擎均匹配固定 SHA-256 和 Apache-2.0 LICENSE。Windows wheel 的当前源文件、原生程序、LICENSE 与平台标签已校验，既有删除的 `rce.md` 未从缓存重新带入。

新的 **2.5.3 / UI build `6d12093b070bf30f`** 交付不沿用同日早期 build `5045501ca869f5d2` 的哈希：

| 文件 | 大小 | SHA-256 |
|---|---:|---|
| `dist/Reverie-Portable-x64.exe` | 438,277,496 bytes | `69369317231615fb655e77e8e045c3ec8510eafa9cf4f45cb62ea14660aff8da` |
| `.runtime/computer-use-packages-final/reverie_cli-2.5.3-py3-none-win_amd64.whl` | 7,858,062 bytes | `8555165805e6d7594d0b245bb141d10614c679bc5198a5a3b71f4da4777601e3` |
| `ReverieCli-ui/.kernel/reverie/reverie.exe` | 14,317,359 bytes | `cc7645e86ceecfaad08798a9664daf625e14e164c0cbeef05da38b62375e2146` |

目录包为 `ReverieCli-ui/release/win-unpacked/`，需要保持整个目录。最终内核的 Harness² 14 次 CLI 执行重新通过；目录包 CLI 在仅保留 Windows 系统 PATH 的环境成功输出版本与 help。完整元数据及结果见 [同名 JSON](computer-use-live-harness2-2026-11-05.json)。限定修改路径的 `git diff --check` 通过；没有重写既有构建脚本的 CRLF，也没有改动既有删除以外的用户文件来清理工作区。

当前包的内核启动、版本、CLI help、嵌入源码和原生引擎完整性可以独立验证。由于本轮 Computer Use 已被停止，新的目录包及便携包未重新执行界面输入/截图预览验收；早期包的通过记录保留为历史证据。未进行全新 Windows 虚拟机验收。


Git publication follow-up: these records describe the earlier desktop runs. The later authorized source publication, NVIDIA refresh, isolated-source checks and rebuilt artifact are documented in [nvidia-refresh-2026-11-05.md](nvidia-refresh-2026-11-05.md). Statements above that Git had not been published apply to the earlier run, not the final publication.
