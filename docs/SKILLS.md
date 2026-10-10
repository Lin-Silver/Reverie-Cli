# Skills 使用与边界

按 2026-10-05 的本地代码核对。Skill 是磁盘上的工作流说明，不是独立可执行服务。工具、SDK、模型、模式或授权依赖仍须可用。

## 发现与读取

`SKILL.md` 使用 YAML frontmatter 描述 `name` 和 `description`，正文按需读取；可附带 `agents/*.yaml`、references、scripts 和其他资源。首次只把精简元数据交给模型，完整正文通过 `skill_lookup(operation="inspect")` 分块读取。元数据可用不等于正文已读完或脚本已执行。

发现来源与同名解析顺序见 [配置](CONFIGURATION.md#skills)。同名 Skill 由前面的来源获胜；被遮蔽者仍可在页面查看来源，但不作为可按名称读取的第二个 Skill 暴露。`policy.allow_implicit_invocation: false` 排除自动选择，显式固定仍可使用。

## 固定必须使用的 Skill

| 指令 | 行为 |
| --- | --- |
| `/skills` / `/skill` | 查看目录及固定状态 |
| `/skill apple-design` | 固定指定 Skill |
| `/skill pin apple-design` / `/skill use apple-design` | 显式固定 |
| `/skill unpin apple-design` / `/skill remove apple-design` | 解除一个固定项 |
| `/skill clear` | 清空固定项 |

Desktop 输入 `/skill ` 即显示候选；选择后变成“必须使用”标签，不发送为普通聊天。最多固定 **4** 个；已固定、被遮蔽或超出上限的候选不可重复加入。固定后系统提示要求每轮先读取对应 Skill、遵循流程，不能由模型随意换成另一个 Skill。

每轮开始时，核心重新解析固定项并读取完整 `SKILL.md` 正文，加入本轮系统消息，同时记录名称、SHA256、字符数和完整读取状态。缺失、空正文或总正文超过 128000 字符会阻止本轮执行，不能悄悄降级为未读取；修改后的正文在下一轮生效。

这保证了主正文加载，不保证模型按语义遵循每一步，也不表示 references / scripts 自动执行。标签表示选择已生效；本轮加载记录与实际工具 / 结果共同用于检查执行。未固定 Skill 仍使用渐进发现 / inspect 分块读取。

## 持久化和模式

| 场景 | 当前行为 |
| --- | --- |
| Desktop 未创建会话的草稿 | 写入核心项目缓存 `desktop/draft-skills.json`，首次创建会话继承 |
| Desktop 已有会话、切换、重启 | 使用 `session.metadata.pinned_skills` 恢复；普通新会话清空 |
| 缺失 Skill | 保留未解析 pin 并提示失效，不静默换成其他包 |
| 分叉 / 自动轮换 | 继承相同任务的 pin 列表；副本与原会话的后续修改独立 |
| 独立 CLI 变更 / 重启 | pin 变更立即保存到所属会话，启动 / 加载时恢复；普通新会话清空 |

部分内置包按模式提供，例如 `reverie-engine` 仅用于 Gamer。Writer 不提供通用 `skill_lookup`，Computer Controller 的发现工具也受模式工具集限制；固定正文由核心加载，不会因此开放被模式禁用的工具。模式不适用的固定项保留为未解析状态并阻止执行，需解除或切换到适用模式，说明参见 [Writer](writer_mode.md) 和 [桌面控制](COMPUTER_CONTROLLER.md)。

## 内置设计 Skills

从 [emilkowalski/skills](https://github.com/emilkowalski/skills) 固定于 `e8a175de22ae1e49370fc144c1f3bb9aeedf988d`，14 个包及支持文件随 Reverie 打包，保留 MIT 许可与 [来源 / 文件哈希](../ReverieCli-py/reverie/builtin_skills/emilkowalski-source.json)：

| Skill | 主要用途 |
| --- | --- |
| apple-design | Apple 风格的界面层级、交互和物理运动原则 |
| emil-design-eng | 组件细节、反馈、排版与界面打磨 |
| animate / animate-expo | Web / React Native 动画实施 |
| animation-vocabulary | 动画效果的术语查找 |
| ask-sonner | Toast 选择、生命周期与样式 |
| break-ui | 长文本、空数据、大列表和窄窗口压力检查 |
| find-animation-opportunities | 只读识别适合添加动画的交互 |
| improve-animations / review-animations | 动画审查、优先级与改进建议 |
| mobile-native | 移动网页的交互细节 |
| pick-ui-library | 根据前端任务选择组件库 |
| prototype | 用户要求时制作可切换的多种 UI 原型 |
| write-swift | Swift 实现与并发设计 |

默认 Reverie 模式实测 17 个内置 Skill，计数会随模式、插件、用户和仓库目录变化。Codex 本身的 `~/.codex/skills` 安装与 Reverie 的内置目录是两个独立位置；不能把安装到 Codex 当成 Reverie 已发现该包。

## 打包与检查

当前 [setup.py](../ReverieCli-py/setup.py) 递归收集内置文件，并排除 reports、Python 字节码及工具缓存；PyInstaller 使用自己的 [spec](../ReverieCli-py/reverie.spec) 打包。不能继续使用旧说明“只包含 SKILL.md、agents YAML 和 references Markdown”。

验证来源、文件完整性、脚本 / 引用资源、遮蔽和模式时使用 `test_design_skills.py`、`test_skill_packaging.py`、`test_skill_resources.py`、`test_skill_shadowing.py` 和 `test_skill_modes.py`。固定状态验证见 `test_skill_pinning.py`、`test_desktop_bridge.py`；单元测试通过不能替代真实模型遵循流程的证据。
