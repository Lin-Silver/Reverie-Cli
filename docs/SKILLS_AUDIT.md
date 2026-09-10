# Skills 系统检查记录

检查日期：2026-09-08 至 2026-09-09。环境：Windows、项目 venv 中的 Python 3.10.11。
检查基线为 `main` 的 `be90cab`，远端 `origin/main` 也已核对为同一提交。
本记录对应经用户审阅批准的改动；验证结果基于提交前的工作区源码。

## 已完成的修复

| 问题 | 修复与验证 |
| --- | --- |
| UTF-8 BOM 导致 `SKILL.md` 元数据未解析 | 统一使用 `utf-8-sig` 读取，验证名称、描述、正文和显式调用。 |
| 中文关键词搜不到描述或正文 | 增加原文短语匹配，覆盖中文描述、正文以及无匹配查询。 |
| 非法资源路径直接抛异常 | 资源路径解析纳入错误处理；继续限制在技能包内，并保留二进制、编码及 2 MiB 上限检查。 |
| 内置技能的嵌套参考资料被 Git 忽略 | 为 reverse-skill 的嵌套 references 添加精确例外，227 份参考文件恢复为可提交内容。另有一份上游 reports 文件仍按上游规则忽略。 |
| photo-to-3d 引用了常规模式不可用的工具 | 将缺失参考图时的询问改为实际可用的 `userInput(question, reason)`。 |
| 内嵌浏览器 DevTools 本机请求误走代理 | 仅对本机 CDP HTTP 请求关闭环境代理；实测启动、输入、点击、页面读取、截图、控制台和关闭会话成功。 |
| Windows 内核信息 arch 为空 | 当 `platform.machine()` 为空时使用 Python 构建平台信息，覆盖 x64、arm64、ia32。 |
| Engine 端到端测试的独立探测误走代理 | 测试探测使用与运行时一致的直连方式；真实 Engine 任务生命周期测试通过。 |
| 递归打包收入 reports 和缓存 | setup.py 和 PyInstaller 数据收集排除 reports、Python/pytest/mypy/ruff 缓存，保留磁盘上的原文件。 |
| 桌面文件改动状态归并错误 | 根据操作前后文件是否存在归并状态；覆盖空文件新增/删除、删除后重建、恢复原内容，以及创建后删除。 |
| 跨模式提示要求调用不可用工具 | 保留 Skills 浏览及固定；Writer 和 Computer Controller 在模型提示、CLI 与桌面显示执行限制和切换方式。工具切换模式后立即刷新 Skills 模式。 |
| 打包目录本身位于 reports 下时遗漏全部 Skills | 排除规则只检查技能树内的相对路径，覆盖 reports/checkout 构建位置。 |
| 差异行数与实际预览不一致 | 内容以 ++/-- 开头仍正确计数；按最终可见预览统计截断行数，保留文件末尾无换行标记。 |
| 切换会话后保留旧的文件预览错误 | 切换会话时同时清除错误和改动；验证迟到请求不会污染新会话。 |
| 截图回退后仍宣称 full_page | 成功回退为视口截图时返回 full_page=false，覆盖两种截图结果。 |
| 错误弹窗太小、停留太短 | 右下角错误弹窗最多 520px 宽、至少 15px 字号，停留 12 秒，支持手动关闭、长文本换行与选择复制；适配窄窗口。 |

将原先放在 `test_desktop_changes.py` 中的两项 Skills 测试移入
`test_skill_resources.py`，桌面状态测试与 Skills 资源测试各自维护。
新增的打包和本机代理验证分别位于 `test_skill_packaging.py`、
`test_browser_controler_proxy.py`。

## 验证证据

| 检查 | 结果 |
| --- | --- |
| 修复前 Python 全量测试 | 1537 通过、2 失败；失败分别为 arch 为空、Engine 独立 HTTP 探测被代理干扰。 |
| 最终 Python 全量测试 | 1575 通过、1 跳过，359.70 秒；使用项目 venv，正常 pytest 配置。 |
| 最终桌面端 Vitest | 131 通过、1 跳过，34.27 秒；使用默认测试进程配置，无启动超时。 |
| 桌面真实 Engine 集成 | 显式指定复制到 dist 审计目录中的 Engine 后，默认跳过的 1 项测试通过，15.62 秒；验证 SDK bridge 的发现、连接、动态工具、停用及正常关闭。 |
| 桌面端类型和 i18n 检查 | 通过。 |
| Electron 主进程及渲染器生产构建 | 通过；存在既有的 JS chunk 超过 500 kB 提示。 |
| reverse-skill 路由 | 175/175 基准用例通过，使用实际 PowerShell 路由脚本。 |
| reverse-skill 文档分块读取 | 44 份路由目标及 2 份核心文档，合计 266 块，46/46 完整重组与原文件一致。 |
| Wheel 资源清单及解包导入 | 当前 Python 源码的 604 个应发布内置资源全部存在且逐文件内容一致；报告与缓存为 0；4 个内置 Skills 均能发现，46 份文档完整读取、中文搜索及 Writer 固定/切换提示通过。 |
| 源码发布包 sdist | 同样包含全部 604 个内置资源，内容逐文件一致，无报告或缓存。 |
| PyInstaller 数据收集 | 执行 spec 中实际的收集函数及 Skills 调用，确认参考资料保留、报告缓存排除。未重新构建完整 exe。 |
| 浏览器真实交互 | 独立 Chromium 页面中的输入与点击改变了标题，DOM 与截图均观察到预期文本，会话已关闭。 |
| 错误弹窗布局 | 使用实际项目 CSS 的独立 Chromium 布局检查：1280px 与 360px 窗口、深浅两种主题均无横向溢出，字号 15px，宽度分别为 520px 和 324px。交互及计时另由 App 回归测试覆盖。 |

Python 跳过项为符号链接越界验证：本机不允许创建符号链接。
桌面全量测试的跳过项为需要显式指定 Engine 可执行文件的集成测试，已单独启用并通过。
绝对路径、普通目录穿越、非法路径、编码、二进制和大小限制均已验证。
浏览器全页截图在本次最小化窗口测试中回退为视口截图，工具已返回回退说明；
本次证据不证明长页面全页截图能力。

本地日志和测试产物放在仓库 `dist/skills-audit/` 以及
`dist/skills-audit-python-current.log`、`dist/skills-audit-ui-current.log`、
`dist/skills-audit-ui-build.log`，不纳入源码提交。
Wheel 构建依赖仅临时安装到 `dist/skills-audit/build-tools/`。
审阅源码的 wheel 和清单位于 `dist/skills-audit/wheel-reviewed/`。
最终候选源码清单及逐文件 SHA-256 位于 `dist/skills-audit/review-inventory.json`，
共 625 个文件（包含新导入的上游资源）。本项目代码及适配层的暂存差异空白检查通过；
新导入的 upstream 原文保留上游尾随空格和末尾空行（包括 Markdown 硬换行），
全范围 `git diff --cached --check` 会报告这些格式问题，不对上游资料批量重排。

## 内置 Skills 的可用范围

| Skill | 已确认范围 | 未覆盖范围 |
| --- | --- | --- |
| browser-controler | 发现、调用说明、真实独立浏览器交互、页面和视口截图证据。 | 任意外部站点、真实登录/上传流程、长页面全页截图。 |
| photo-to-3d | 元数据、完整工作流正文、全部参考资料、工具名称以及浏览器检查基础链路。 | 未用用户照片完整执行八阶段建模，未证明模型生成质量。 |
| reverie-engine | Gamer 模式发现与模式门控；全量测试中的游戏循环、资源与真实 Engine 任务生命周期。 | 未重新发布独立 Engine 或 CLI exe；不将单元测试等同于任意游戏交付。 |
| reverse-skill | 作为一个顶层包发现；175 个路由用例、44 个路由文档、核心资源和发布完整性。 | 外部逆向工具/MCP 未安装或启动；未逐个执行所有安全分析场景。 |

`reverse-skill/UPSTREAM.md` 已记录 5 份导入时被杀毒软件阻止的参考文档缺失。
依赖这些文件的流程不能宣称完整可用；本次没有尝试补取或绕过该限制。

跨模式策略已完成：保留通用 Skills 的发现、浏览和固定。
Writer 显式提示先切换再检查技能，Computer Controller 提示执行依赖工作区工具的流程前切换；
使用 `switch_mode` 或 `/mode reverie`，固定状态会保留。
Reverie、Atlas、Gamer 保留原工具能力；reverie-engine 仍遵守既有 Gamer 模式门控。

## 最终提交范围

包括 Skills 系统与内置资源、模式说明、浏览器及内核修复、打包规则、桌面文件改动预览、
已有桌面侧栏和 Thinking Tool 显示改动，以及本次新增的错误弹窗调整与回归测试。
保留 reverse-skill 的上游归属、许可证和缺失文档说明。
不包含 dist 下的构建产物、测试日志、缓存和临时依赖。

用户已授权自主修复检查中发现的问题，并于审阅后明确批准提交。
提交及推送目标为当前仓库的 `main`，不创建 PR。
