# Computer Use 实施与验收记录（2026-11-05）

本文件保留早期交付事实；最新的实机、真实模型、Harness² 与重建包结果见 [补充验收记录](computer-use-live-harness2-2026-11-05.md)。物理操作、文本模型和资源管理器的新结果已更新，不能继续将下文的早期限制当作当前结论。

## 结论与范围

本轮实现的是以无障碍树和语义操作为默认路径的内置工具体系。它不依赖截图或像素匹配完成普通桌面任务。截图、图片坐标和物理输入是显式补充能力。`computer_type_text` 默认使用上游无头语义策略，`physical=true` 才允许物理输入。

源码、Windows x64 原生引擎、模型/权限/会话整合、UI 展示和构建分发已经落地。受控应用、Chromium、记事本以及真实打包界面已有验证记录。**原计划的全部环境验收尚未通过**：物理前台接管、资源管理器目标观察、真实提供方模型完整任务、多显示器和其他 DPI 场景仍有明确限制，详见下文。

没有执行 Git 提交、推送或发布。开始工作时已有的构建脚本、任务工具、界面修改和 `rce.md` 删除均予以保留。

## 已实现的关键约束

- 同一组 29 个工具注册到两种模式；10 个旧入口隐藏并转接同一运行时。
- argv 子进程、UTF-8 stdin、隐藏原生进程、固定校验值、有限超时、随机 session 和 RunControl 取消。
- 会话切换、清空和恢复历史均使旧 ref、数字索引、图片记录失效。
- 明确的桌面权限声明；子代理既看不到 schema，也不能直接调用桌面入口。
- ref 优先；坐标记录包含截图尺寸、裁剪和可证明的可见窗口边框原点。拒绝过期、非视觉、越界、身份/几何变化、失焦或被其他窗口遮挡的坐标操作。
- 保留交付状态和重试约束；超时、无效 JSON 和异常退出不触发动作重放。Shell 启动后观察失败不能将已交付请求改成“未交付”。
- 条件等待不向模型发送整棵树。大结果截断和上下文压缩保留交付、目标及观测完整性。
- Chat、Responses、Anthropic 的工具结果/图片适配；历史保存轻量图片标记，当前会话在请求前装载图片。图片不因历史恢复而重新取得坐标权限。
- Computer 模式移除 NVIDIA 强制选择；保留 NVIDIA 提供方本身。UI 显示目标和真实交付状态。
- 操作诊断及 Electron 运行日志仅保留桌面动作元数据、交付状态和错误码；不重复保存输入正文、剪贴板内容或图片 base64。导出日志再次脱敏仍保留交付证据，实时界面事件不受影响。

## 自动化验证

| 检查 | 结果与边界 |
|---|---|
| 完整 Python 回归 | **3130 passed、7 skipped**；后续限定修复另跑下列受影响测试 |
| 最新桌面运行时、图像、权限、兼容、生命周期、适配、预览、诊断 | **150 passed**；`.runtime/computer-use-python-final-tests.log` |
| 桥接、NVIDIA、提示词及桌面相关组合 | **290 passed** |
| UI 全套 | **475 passed、1 skipped** |
| 最终文件预览、桌面结果及运行日志相关 UI 测试 | **20 passed**；`.runtime/computer-use-ui-final-tests.log` |
| UI 类型和 i18n 检查 | 通过，1064 个翻译键、82 个模板 |
| Python 内核 | 真实 PyInstaller Windows x64 onedir 构建通过 |
| UI | 真实 TypeScript/Vite 构建通过 |
| Python wheel | Windows 平台标签 `py3-none-win_amd64`，验证原生程序及 LICENSE 入包 |

专门覆盖了重复名称、身份变化、过期 ref/image、裁剪缩放、DWM 不可见边框、未知交付不重放、取消前不启动/取消中保留已交付结果、子代理拒绝、严格参数校验，以及大错误描述不能吞掉交付元数据。

Responses 和 Anthropic 使用实际代理循环、模拟提供方做两轮请求测试，检查第二次请求确实包含截图/剪贴板 PNG，历史不含 base64。它们验证协议适配，**不等同于真实模型完成任务**。

整仓 `git diff --check` 仍报告既有根目录 `build.bat` CRLF 行的 trailing-whitespace；本次 Python 生产文件、UI 变更和 Electron 文件的限定 diff 检查通过，没有为消除该既有告警重写构建脚本。

## 真实桌面验证

最新受控应用记录：`../../.runtime/computer-use-20261105-052305/`。

- 中文、Windows 多行文本的语义写入和精确文件回读。
- 单次按钮调用，随后通过条件等待确认计数只增加一次。
- 复选框目标状态、下拉框展开/具体 option 选择/折叠、树节点展开/折叠。
- 两个同名控件均返回；多个窗口下关闭应用返回歧义错误，不选择第一个。
- 文本和 PNG 剪贴板写入、读取、清空；测试应用保存并恢复原始剪贴板格式。
- 独立截图、过期图片拒绝；观察不需要窗口激活。
- WinForms 的插入式语义 `type` 不可用，返回 `not_delivered`，没有自动物理回退。该控件的 `set_value` 可正常工作。

真实应用记录：`../../.runtime/computer-apps-20261105-050726/`。

- **Chromium**：独立测试 profile、本地 HTML；无障碍观察、中文多行语义写入、属性回读、截图通过，未访问日常浏览器 profile。
- **记事本**：打开独立测试文档、完整无障碍观察、截图及正常关闭通过。未覆盖物理输入。
- **资源管理器**：启动请求返回后，两个独立尝试均未在有限等待内观察到唯一目标目录窗口；未将启动请求成功当作窗口验收成功。

当前机器只有一个可用显示器，1920×1080、scale=1。没有双显示器或其他 DPI 的真实验收。

## 性能样本

`computer_use_smoke.py` 在同一受控任务后连续执行 8 次精确 `computer_find`，以中位数为 p50、nearest-rank 为 p95。此为小样本本机观测，没有旧版本同负载基线，不作整项任务加速倍数承诺。

| 样本 | p50 | p95 | 初始树 JSON 字符数 | 语义阶段图片传输 |
|---|---:|---:|---:|---:|
| 04:55:20 | 594 ms | 688 ms | 13,959 | 0 |
| 04:58:06 | 477 ms | 2,172 ms | 14,408 | 0 |
| 05:23:05 | 477 ms | 5,516 ms | 14,408 | 0 |

后两轮与构建/回归在同一机器运行，尾延迟明显波动。完整命令耗时在各目录 `summary.json` 的 `native_calls` 中。纯语义阶段没有调用 screenshot；可选图片阶段单独记录。固定脚本不消耗模型往返；打包链路测试的本地模拟服务用了三个模型请求，其中第三个携带一张图片。

## 打包链路

`computer_use_package.py` 启动真实 Electron、真实 Python 内核及包内 agent-desktop，使用新建配置、隔离 session、独立桌面 profile 和本机确定性 HTTP 服务。测试时 PATH 只保留 Windows 系统目录，不含 Python、Node 或 agent-desktop。

已验证 Computer 模式模型选择器可切换到 `package-vision`；实际后续请求均使用该模型 ID。两种模式都返回 29 个 `computer_*` 工具，新 schema 中没有 `get_app_state`。真实状态与截图调用成功；第三次请求包含图片。它证明分发/适配链路可用，不证明模型推理质量。

实机截图检查发现专用数据目录的图片被通用工作区预览拒绝；已增加只允许当前项目或 Computer 专用数据目录下有效 PNG 的只读解析，不放宽普通文件编辑权限。最终打包运行结果及哈希另见本目录同名的交付清单 JSON。

最终目录版 `5045501ca869f5d2` 的记录在 `.runtime/computer-package-20261105-054524/`：模型切换、两种模式各 29 个工具、两张工具卡片、真实图片预览及重新加载均通过，没有浏览器错误。验收脚本现已等待会话保存完成，避免在实时卡片切换为历史卡片时点击，并在失败时返回非零退出码。另通过 PyInstaller archive reader 对照当前源文件编译结果，确认内核中 16 个桌面及整合模块的字节码匹配当前源码，记录为 `.runtime/computer-use-kernel-source-check.json`。

最终便携包也已通过同一流程，记录在 `.runtime/computer-package-20261105-055331/`，构建号同为 `5045501ca869f5d2`。在全新目录、仅 Windows 系统 PATH 下完成首次解压、真实内核和原生引擎调用、模型切换、图片传递、预览及刷新。首次解压耗时 **45.7 秒**；验收脚本分别等待解压完成标记和界面启动，解压阶段上限为 180 秒。便携包解压后的内核、UI app.asar 与目录版逐字节哈希一致，四处原生引擎副本均匹配固定 SHA-256。没有进行全新操作系统虚拟机验收。

交付文件：

| 文件 | 大小 | SHA-256 |
|---|---:|---|
| `dist/Reverie-Portable-x64.exe` | 438,301,311 bytes（约 418 MiB） | `2cd4c9b7e1f55a1085fbc20123853493e3bf953ac6465bd77443a0585c475a01` |
| `.runtime/computer-use-packages/reverie_cli-2.5.3-py3-none-win_amd64.whl` | 7,857,057 bytes | `b84e7fa9c19c9edf4e5c570b9749367b666efc642a3922fe88b95a3cd96626ea` |

目录版及内核也保留在 `ReverieCli-ui/release/win-unpacked/`、`ReverieCli-ui/.kernel/reverie/`；它们运行时需要同目录的配套文件。完整清单为 [computer-use-2026-11-05.json](computer-use-2026-11-05.json)。wheel 中 16 个相关源文件与当前源码一致，原生程序、LICENSE 和来源 receipt 已验证入包；既有删除的 `rce.md` 没有被旧构建缓存重新带入 wheel。

## 尚未通过的验收

1. **物理前台控制**：原生 `focus-window` 和独立 Computer Use helper 均无法激活测试窗口。窗口截图和无障碍操作仍可工作；坐标输入正确拒绝失焦目标。没有声称真实拖动、鼠键接管、开始菜单/托盘输入和键盘取消释放流程已通过。
2. **真实模型端到端任务**：已使用现有配置发起真实请求，未改写用户配置。结果包括当前 `nemotron-3.5-lightning-free` 429、`sensenova-6.7-flash-lite` 404、`ZhipuAI/GLM-5` 无可用提供方、`MiniCPM-V-4.6-Thinking` 401、`claude-opus-5` 403、`devstral-latest` 429、`stealth/ox-alpha` 已退役 404。均未进入成功的工具任务循环。完成此项需要一个当前可访问的文本模型和视觉模型。
3. **资源管理器及环境矩阵**：目标目录窗口未确认；多显示器、其他缩放和全新 Windows 虚拟机未测试。
4. **平台范围**：Windows ARM64、macOS、Linux、通知中心管理和操作动画不在本轮交付声明内。

最小补充条件为：允许目标窗口取得前台的交互桌面、可用的模型访问权限/配额，以及对应多显示器/DPI 或干净虚拟机环境。源码中的验收脚本可在这些条件具备后直接重跑。


Git publication follow-up: these records describe the earlier desktop runs. The later authorized source publication, NVIDIA refresh, isolated-source checks and rebuilt artifact are documented in [nvidia-refresh-2026-11-05.md](nvidia-refresh-2026-11-05.md). Statements above that Git had not been published apply to the earlier run, not the final publication.
