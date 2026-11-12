# WStyle Cards 使用指南

WStyle（Writer Style）把文笔、叙事、人物、关系和类型机制保存为可组合的 Markdown Cards。`/wstyle` 是 Writer 模式的原生命令：终端与 Desktop 使用同一 Python 实现，选择结果会进入下一轮实际模型请求的 System Prompt。普通正文练习、原生小说章节和中断续写都使用当前有效组合。

WStyle 管理完全离线。正文生成使用当前模型；只有明确执行 `review` 或 `extract` 才额外调用模型。文学效果取决于模型、故事、上下文与编辑，软件不会把字数或关键词统计当作作品质量评分。

## 开始使用

```text
/mode writer
/wstyle list
/wstyle use delicate-prose dual-heroines gl-romance-beats --global
/wstyle current
```

随后提出故事要求，例如：

```text
创建原生小说 harbor《旧水位》。两名成年女性各有职业目标，在修复供水过程中逐步重建信任。
先完善世界观、人物、故事架构、风格指南与章节规划，再生成第一章。
每章至少5000字，目标10000字；具体场景和行动后果支撑篇幅，避免重复填充。
```

`serial_novel` 创建或恢复项目后会绑定当前对话。此时 `/wstyle use ...` 修改该小说的覆盖；`--global` 始终修改应用默认。继续同一小说可使用：

```text
/wstyle current --novel harbor
/wstyle use delicate-prose commercial-serial-engagement --novel harbor
恢复 harbor，读取已提交章节、人物状态和当前控制卡，再继续尚未完成的场景。
```

切换不重写已有草稿或已提交章节。保留的短稿继续通过原生 `append_content` 追加，新段采用新组合；需要修稿时明确说明章节和修订目标。已经完成的项目仍遵守原生生命周期限制，不能通过风格命令绕过完成状态。

## 安装目录与内置资源

Cards 位于 `<app_root>/.reverie/wstyles/`。源码运行默认 `app_root` 是仓库 `dist/`；独立 EXE 使用自身目录，便携 GUI 使用启动器所在目录，安装版使用安装目录。Desktop 选择其他核心数据根目录时，以所选核心 app root 为准。`/wstyle current` 显示实际目录。

首次使用会安装六张资源，默认均关闭：

| ID | 层次 | 主要作用 |
| --- | --- | --- |
| `delicate-prose` | prose | 具体细节、自然句式、克制情绪与潜台词 |
| `dual-heroines` | character | 两名女主各自的目标、判断、声线与成长 |
| `ensemble-heroines` | character | 女性群像的叙事权重、动机和关系网络 |
| `gl-romance-beats` | relationship | 由具体互动支撑的信任与感情变化 |
| `isekai-subversion-comedy` | genre | 具有因果的信息差、制度限制与反套路喜剧 |
| `commercial-serial-engagement` | narrative | 开篇期待、情节推进、信息释放和章节回报 |

同名用户文件不会被覆盖。`.bundled.json` 记录已经安装的资源：用户随后删除某张内置 Card，重启或升级不会把它重新装回。恢复已删除资源可从[源码资源目录](../ReverieCli-py/reverie/writer/wstyle_cards/)复制所需文件。安装升级和卸载保留执行目录下的 `.reverie`；备份时仍应同时备份小说原稿、核心配置和 Desktop 草稿存储。

## 完整命令

| 命令 | 行为 |
| --- | --- |
| `/wstyle`、`/wstyle current` | 当前作用范围、保存和有效顺序、哈希、预算与问题 |
| `/wstyle list` | 所有 Cards 的名称、简介、层次、有效性和启用状态 |
| `/wstyle show <id>` | 阅读 Card，不启用 |
| `/wstyle use <id...>` | 替换组合，保留指定顺序 |
| `/wstyle add <id>` | 追加一张；重复添加不会重复注入 |
| `/wstyle remove <id>` | 只移除指定 ID，也可清理已经丢失的 ID |
| `/wstyle off` | 保存空组合，保留 Card 文件 |
| `/wstyle inherit` | 删除当前小说覆盖，重新继承应用默认 |
| `/wstyle new <id>` | 创建可编辑的基础 Card，已有文件不覆盖 |
| `/wstyle new <id> --from <source-id>` | 复制已有 Card，修改新 ID 与名称，保留其他元数据 |
| `/wstyle review [<novel-id>] --chapter <n>` | 对草稿或已提交章节保存编辑建议 |
| `/wstyle extract <new-id> --sample <path>` | 从明确提供的样本提取新 Card，保留来源且不启用 |

选择和查询支持 `--global` 或 `--novel <id>`，两者不能同时使用。未绑定活动小说时，选择命令修改应用默认；小说 `active_wstyles` 缺失代表继承，`[]` 代表主动关闭。

路径含空格时加引号；Windows 反斜杠路径可直接使用。审稿和样本提取还支持 `--start-line <n>`、`--end-line <n>`。多个样本重复使用 `--sample`：

```text
/wstyle review harbor --chapter 1 --start-line 10 --end-line 90
/wstyle extract my-scene-prose --sample "samples/自写片段一.md" --sample "samples/自写片段二.txt" --layer prose --source-note 自写原创练习
/wstyle show my-scene-prose
/wstyle add my-scene-prose --novel harbor
```

Desktop 在输入框执行这些命令，结果显示于可滚动的 WStyle 面板。运行中的创作任务需要先停止，再修改组合或发起审稿；等待命令时新输入的草稿会保留。命令失败保留输入，便于修正。Card ID 候选来自实际文件目录。

## Markdown 格式

文件名必须与 `id` 一致，例如 `my-prose.md`：

```markdown
---
schema: reverie.writer.wstyle.v1
id: my-prose
name: 克制的近景
description: 以具体动作和注意力选择表现情绪
layer: prose
version: "1"
directives:
  sentence_rhythm: varied
incompatible_with: []
---

# 原则

用视角人物当前在意的细节组织描写。对白中的停顿和回应应改变行动或关系。
在必要的位置保留长句和安静场景；删去没有新增含义的重复解释。

# 原创示例

她把尚有余温的票根收进口袋，给对面的空座让出一点地方。
```

必须有 `id`、非空 `name` 和 `layer`。缺省 `schema` 按 v1 处理；未知且可序列化为 JSON 的元数据会保留。`layer` 为 `prose`、`narrative`、`character`、`relationship`、`genre` 之一。

ID 支持规范化的中文及其他字母、数字、连字符和下划线，最多80字符。拒绝 Windows 保留名、路径分隔符、路径穿越、符号链接和重解析点。支持 UTF-8 BOM 与 CRLF；计算 Card 内容哈希前会去掉 BOM 并统一换行。

单个文件不超过64 KiB，正文不超过16,000字符，完整组合提示词不超过24,000字符。另使用 UTF-8 字节数作为保守 Token 上界，将 WStyle 限制在有效上下文窗口的25%内；有效窗口取配置上限与活动模型声明上限中的较小值。这不是实际分词统计。主动选择超限组合会拒绝保存；已保存组合在 Card 被修改、丢失、损坏或预算减少后按顺序保留可用整张 Cards，并明确显示未生效项，不截断规则，不静默清空保存列表。

## 组合与优先级

选择顺序是组合顺序。无冲突规则共同保留；只有冲突的创作偏好以后选 Card 为准。`directives` 明确记录维度的最终来源。软件不理解任意自然语言规则的全部语义，未结构化的冲突仍需要模型遵循组合约定并由编辑检查。

`incompatible_with` 声明的组合会拒绝启用，检查是双向的；同层 Cards 提示警告，允许继续。例如双女主和群像卡可能对主角结构有实质冲突，内置人物卡已声明互不兼容。

当前用户明确要求、既定人物身份、时间线、世界规则和小说风格指南约束 Cards。Card 是创作数据，不能改变工具权限、执行程序、切换 Provider、泄露秘密或自行授权改写。中文句子和示例会作为独立创作块组织，旧会话里的风格 System 快照不再重播进新请求。

## 生效、缓存与追溯

每轮发送前重新取得当前组合。目录和文件未变化时复用索引与解析结果；修改文件的时间、大小或身份变化后重新校验，删除和新建也会更新列表。通常无需重启。重新启动读取已保存的顺序与小说覆盖。

`current` 反映当前可用组合，并非“模型已经遵循”的证明。控制卡记录准备时的 Card ID 和哈希；生成请求记录实际使用的快照；草稿与提交记录的 `wstyle_segments` 保存原稿和追加段的来源。没有实际请求证据的旧稿会明确标为未验证来源。审稿、风格切换和导出不会把这些元数据插进阅读版 TXT。

损坏的 `.bundled.json` 会报告资源安装问题，继续加载已有合法 Cards；不会覆盖该文件。修复安装记录后重启。损坏的应用配置无法安全保存时会拒绝写入；合法小说覆盖与合法 Card 不应因一个坏文件而丢失。

## 审稿与样本提取的边界

审稿优先读取保留草稿，否则读取已提交正文。行号对应去掉管理标题后的正文行。输入片段最多16,000字符，项目事实与指南总预算10,000字符，省略整份文档时明确记录。另纳入当前章节之前最近三章的摘要、事件、人物、关系和时间线记录，合计最多8,000字符；不纳入当前章或后续章，不截断超限记录，报告会列出未纳入的前章。已保存的摘要不等于前章全文，证据不足时仍需核对原稿。报告保存原文快照、原文与片段哈希、请求、模型输出、机械检查和建议，位置及引用逐项与原文核对。每条引用须来自单独一行的连续原文，不能拼接多行、改写或用省略号代替。最新且仍匹配原稿的建议可出现在 `serial_novel(context)`，只用于明确要求的修订。

提取接受1–8个明确指定的 UTF-8 `.txt` / `.md` 文件或行范围，每个文件最多1 MiB、合计片段最多16,000字符。保存文件和片段哈希、数量、范围、来源说明、观察及局限。新 Card 描述可迁移机制；拒绝与样本连续重合48个非空白字符的正文。这只能识别部分直接复制，不能证明原创、授权或跨作品普遍规律。

两项辅助调用只发送明确组织的正文、样本和小说上下文，不带聊天历史、聊天记忆或工具，也不执行模型返回的动作。单次输入最多60,000字符，输出最多32,000字符，审稿请求4,096 Token、提取6,144 Token，超时上限60秒，无自动 API 重试。组合后的输入还要满足活动模型的上下文预算，超限时需选择较小的正文片段。输出未完成、引用不实或格式错误时保留诊断，不生成有效报告或覆盖原稿。普通长篇创作不使用这些编辑预算。

## 编写与验证 Card

优先描述能在具体场景执行的机制：谁注意什么、角色为什么选择、对白怎样改变关系、信息何时释放。写清适用范围、例外和反例，让语言、行动和情绪互相支持。少用“高级、细腻、爆款”等不能落实的标签，不把所有题材强制套入同一种开篇或悬念结构。

从多个合法样本提炼共同机制，记录样本差异和覆盖不足，避免搬运人名、专有设定、原句或作者指纹。用相同模型、设定、目标和主要参数比较关闭、单卡、多卡结果，再阅读具体差异。请求层自动测试和真实生成评测的方法见 [Writer 质量与评测](WRITER_QUALITY.md)，开发入口见 [开发指南](DEVELOPMENT.md)。
