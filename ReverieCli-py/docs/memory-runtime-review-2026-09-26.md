# Memory runtime review — 2026-09-26

本次范围为记忆管理的 remember/list/get/correct/delete/consolidate/conflicts/status、recall/answer、上下文组装、工具执行、模型请求及 Windows 交付。GUI 原生交互及其他产品功能未纳入这轮验收。

## 已修复的逻辑与性能问题

- 记忆操作和只读工具不再触发全工作区 Git 检查点；检查点失败后会恢复 active tool 上下文，并记录失败结果。工具计时包含前置检查点。
- 最近事件从 JSONL 尾部按块读取，找到足够结果即停止；保留原有顺序与筛选语义，支持跨块 UTF-8、长记录、无末尾换行和损坏行。
- 新增记忆直接检查已提交记录与全文索引，不再执行全库排名或增加其他记忆的访问计数。
- 检索只更新访问元数据，不重建全文索引。缓存有界的不可变文本特征，避免多样性排名中的重复分词；时间、置信度、访问次数仍按当前记录计算。
- 无搜索词的列表在数据库中应用范围、类型、会话及数量限制。
- 会话记忆记录所属会话，并在去重、冲突检测与检索中隔离；相同正文不会覆盖其他会话的记录。
- 已被替换或已删除的记录不能通过 correct 或 remember 复活、分叉并破坏历史；只合并仍有效的重复记忆。
- HTTP 和 OpenAI Chat 请求遵守配置的重试次数与退避；关闭 Chat SDK 的叠加重试，非兼容性 4xx 不再重发相同请求。Responses SDK 保留独立的配置重试。
- 一次模型请求复用同一份上下文，随后转换本地图片，避免重复组装；Responses 请求也复用已组装消息。
- 修复运行时的强制工具路由：明确调用记忆工具或修改/删除指定记忆 ID 时，不因正文包含“项目”“测试”等词而强制查代码。修改记忆模块的源代码仍先调用 Context Engine。
- 提示词及实际工具 schema 要求模型自行组织简洁、独立的记忆正文。Memory OS 负责结构化存储；应用没有硬编码用户的记忆正文。

## 本地基准

同一台机器、真实 SQLite/FTS5、2,000 条记忆、50,000 条 JSONL 事件；每项重复五次取中位数。重复检索包含缓存收益。这些数字不是远程模型端到端延迟，构建并行时会有波动。

| 操作 | 修改前 | 修改后参考值 |
| --- | ---: | ---: |
| 最近 20 条事件 | 361.4 ms | 0.258 ms |
| 筛选最近 20 条事件 | 474.8 ms | 0.703 ms |
| 检索 8 条记忆 | 393.5 ms | 110.023 ms |
| 新增记忆 | 464.4 ms | 95.296 ms |
| 列出最近 20 条记忆 | 50.8 ms | 1.940 ms |

参考测量文件：`build/memory-review-benchmark-final.json`。最终运行也会在各自 JSON 报告内记录基准。

## 可重复的真实循环

```powershell
cd G:\Reverie\Reverie-Cli\ReverieCli-py
.\venv\Scripts\python.exe scripts\smoke_memory_runtime.py --config ..\dist\.reverie\config.json --executable ..\ReverieCli-ui\release\win-unpacked\reverie.exe --cycles 1 --report ..\build\memory-smoke.json
```

省略 `--executable` 测源码；改为 `..\dist\reverie.exe` 测独立 CLI；省略 `--config` 只跑本地基准。`--cycles 2` 在同一临时项目重复循环，轮间暂停 60 秒。

循环为：新增中文简洁回答偏好 → 检索 → 修改为中文详细回答偏好 → 再检索 → 删除。直接检查实际数据库、版本、模型生成正文、工具结果和检索输出。没有模拟模型、伪造工具成功或写入用户真实项目记忆。

凭据从指定配置或 `AGNES_API_KEY` 读取，仅通过内存/环境传递；临时配置不含密钥。报告记录实际耗时和源运行中的模型等待时间。

连续请求曾真实触发 Agnes 免费用户的 429 限流，包括“工具已成功、最终模型确认被限流”的情况。因此脚本默认步骤间隔 15 秒；`--step-delay 0` 可以进行无间隔压力测试。间隔单独报告，排除在单步耗时之外，应用运行时没有这个人工间隔。成功的有间隔循环不能证明免费 API 可无限连续请求。

## 验证与交付证据

- Python 相关回归：403 项通过。
- 桌面 Vitest：151 项通过，1 项跳过；UI 编译通过。
- Windows CLI、桌面内核、安装包和便携版按最终源代码重新编译；内核 `--kernel-info` 与 SDK bridge ready/shutdown 协议检查成功。
- 最终源码及交付内核循环的逐步结果保存在 `build/memory-review-source-final.json` 和 `build/memory-review-release-final.json`；更早的源码、目录内核、独立 CLI 循环也保留在 `build/memory-review-*.json`。
- 原 CLI 和便携版备份：`build/memory-review-backups/`。未修改用户的凭据、实际项目记忆或模型选择。

GUI 原生交互没有单独验收；真实测试覆盖与桌面共用的后端执行链。模型有时仍会自主追加记忆 get 调用，外部响应时间和免费限流仍有波动。旧记录如果没有会话 ID，无法可靠猜测所属会话；此修复保留这些旧记录，未迁移或重写用户历史。

最终源码单步耗时：新增 15.307s、检索 7.503s、修改 10.245s、再次检索 18.252s、删除 8.142s；相应记忆工具 9–18ms。交付包内核：28.498s、9.279s、13.570s、12.011s、10.008s；工具 7–17ms。每轮额外的 4 次 15 秒测试间隔共 60 秒，已单独记录，未计入这些单步耗时。两轮最终报告均为成功，工具调用均属于 memory_manager/memory_retrieval。

交付文件的 SHA256 和大小已核对，记录于 `build/memory-review-artifacts.json`：实际 CLI 与暂存 CLI 一致，交付包内核与编译内核一致。
