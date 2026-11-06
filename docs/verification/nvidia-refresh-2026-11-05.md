# NVIDIA、Computer Use 与 Harness2 提交验收（2026-11-05）

本记录对应用户授权同时提交 Computer Use、Harness2 和 NVIDIA 更新。提交范围排除较早的任务清单/活动日志修改及既有 rce.md 删除；混合文件只暂存本次相关内容。为核验实际待提交源码，在 .runtime/publication-check 导出 Git index，保留独立源码、日志和包；原工作区的无关修改保持原状。

## NVIDIA 更新与真实 API

目录现在提供 12 个模型。移除 NVIDIA 官方已弃用的 nvidia/nemotron-3-super-120b-a12b；2026-11-05 实际端点返回 404。新增 Mistral Large 4 和 Nemotron 3.5 Bolt E4B 专用请求 profile，覆盖持久化选择、上下文/输出限制、视觉标记和请求正文。Kimi K3.1 Pro 的官方原型明确不开放程序化 API，因此不提供为可调用模型。

- Mistral：262144 上下文，最大输出 262144、默认 16384；temperature=1.0、top_p=0.95，发送已经实测成功的 reasoning_effort=high，保留工具续轮 reasoning_content。官方 schema 的 none 返回 400，low/medium 实测超时，不暴露这些未经资格验证的选项。
- Bolt：65536 上下文和输出上限，默认输出 16384；temperature=1.0、top_p=0.95；通过 chat_template_kwargs.enable_thinking 设置思考，skip_special_tokens=false 保留解析边界，不发送 Lightning 的 reasoning_budget。普通模型 ID 请求成功，文档中的 stg/ 别名实测 404。
- Bolt 的真实 SDK 工具调用、结果续轮和流式文本全部通过。Mistral 工具调用和结果续轮通过；流式文本与图片检查发生提供方超时，整体视觉/流式资格仍为部分验证。保留 .runtime/nvidia-november-live 和 .runtime/nvidia-november-mistral-refined 的失败记录，不将超时包装为通过。

官方依据见 [模型目录与参数说明](../NVIDIA_CATALOG.md)。检查脚本为 scripts/verification/nvidia_catalog_smoke.py；只存阶段/耗时/状态，不记录 key、思考正文或图片 base64。

## Harness2 针对性修复

固定 google-research/harness2 的未修改提交 6868817518876de8fd170c6a8354daca273b6191。

同一 Bolt 模型、同一合成 inventory-1 任务、相同 30 请求预算和 sequential 模式：初次 CLI 求解成功，但改进模型返回 JSON 缺少 edits，整轮失败。针对该端点支持的结构化输出，改进请求现在声明 JSON schema：必须包含 edits 和 notes，编辑仅限三个既定组件，禁止 guardrails 与未知字段。宿主仍整体校验后才写文件；无对象或缺字段明确报告契约错误。

重测整轮通过：4 次真实 CLI 执行、12 次真实提供方请求、1 条经验记录。前后使用相同内核哈希 a56825b338bb505270fcf04fa1ecdb1ffddd1a3a90d29efc519cf586ed7c8fc6。这个结果验证格式/递归执行可靠性，不证明泛化质量提升。

最终内核的确定性集成重跑也通过：两任务、两递归模式、14 次 CLI 执行、28 次 HTTP 请求、4 条经验记录。记录在 .runtime/publication-harness2-fixture；真实基线与重测分别在 .runtime/publication-harness2-bolt-live、.runtime/publication-harness2-bolt-refined。正式 JobBench/LAB/WorkBuddy 分数仍未运行，score=null；Windows 当前缺少所需 Linux/任务集/judge 环境。此前失败样本与验收限制见 [实机记录](computer-use-live-harness2-2026-11-05.md)。

## 源码与回归

- 当前工作区全仓 Python：3170 passed / 7 skipped，607.25 秒；日志 .runtime/november-publication-python.log。此后新增诊断与改进响应契约测试的最终定向回归为 93 passed。未把全仓数字当作之后增补测试的全仓重跑。
- 实际待提交源码独立检查：365 项 Computer/NVIDIA/Harness/模型请求定向测试通过；之后诊断和契约增补另有上述回归。
- 当前工作区 UI：476 passed / 1 skipped；排除无关本地改动后的待提交版本 UI：473 passed / 1 skipped。后者的 i18n、TypeScript、Electron 主进程和 Vite 生产构建通过。
- 桌面诊断改为复用现有 diagnostic_result；兼容入口返回非对象 JSON 时不再因日志处理抛错，也不复制私密内容。三个错误形状的测试通过。
- 对 Bolt 思考开关做反转变异检查，定向测试正确失败；随后恢复源码。Git diff 检查使用 cr-at-eol 保留 Windows 批处理既有 CRLF。

## 构建与包检查

从待提交源码构建的 2.5.3 内核中，8 个核心模块与源码字节码相符；已移除的 Nemotron 3 Super profile 不在冻结包中。原生程序 SHA256 为 d274667031322e50b9c2b1ab81c2ca46835d52cc932769a5c34bd4d481fd94c3，并保留 Apache-2.0 LICENSE。

内核与目录包均通过 --version、SDK bridge ready/shutdown 和实际离线 NVIDIA 目录请求；仅使用 Windows 系统 PATH 即可运行，返回相同 12 模型。Windows wheel 的模块正文、平台标签和原生程序/许可已核对。新增 pyproject.toml 声明 setuptools>=70.1 与 wheel 的隔离构建依赖；实际从 setuptools 65.5.0 的旧构建 venv 调用 pip wheel 的隔离构建通过，不需要修改该 venv 的 setuptools。

临时源码导出中的既有 rce.md 被 Microsoft Defender 隔离（事件 1116/1117）；本机未恢复它或改动防护设置，包不包含该文件，Git 中原有文档及用户工作区的删除状态保持不变。这是包的资源例外。随后 NSIS 在 261 字符源路径复现失败；便携构建现在使用 Windows namespaced source path，保留原有输出路径约束。

新版 GUI 的真实窗口输入/截图预览验收、纯文本桌面模型门禁、视觉桌面完整任务、取消中物理状态释放、多显示器/DPI、开始菜单/托盘、Chromium 未暴露控件及干净 Windows 机器验收仍未完成。此前 Computer Use 插件的停止/策略终止保持有效，本次未通过其他入口绕过。不能将源码测试、CLI 启动或简单模型请求当作这些验收的通过。


## 本地交付产物

| 产物 | 大小 | SHA256 |
| --- | ---: | --- |
| dist/Reverie-Portable-2.5.3-ComputerUse-NVIDIA-x64.exe | 429092789 bytes | ff9e0eebe67c4c09b9aa39f2b8c7b8ff21e0ebe7401aee96b9bcb2f298821468 |
| .runtime/publication-check/ReverieCli-ui/.kernel/reverie/reverie.exe | 14317376 bytes | a56825b338bb505270fcf04fa1ecdb1ffddd1a3a90d29efc519cf586ed7c8fc6 |
| .runtime/publication-wheel-isolated/reverie_cli-2.5.3-py3-none-win_amd64.whl | 7858521 bytes | 7b414c19414e55af6dda732b745c77d4b53621b21b2d5ca68d605617af5f011d |

目录包在 .runtime/publication-check/ReverieCli-ui/release/win-unpacked，需要整个目录。UI build 为 9ecc1e4b15779c7b；便携解压标记为 6e54cfe9805c8d01，二者用途不同。实际便携入口 --tui --kernel-info 在仅有 Windows 系统 PATH 的新隔离目录启动，退出 0；解压后的内核、app.asar 和 agent-desktop 与目录包逐项哈希一致。这个启动检查没有操作 GUI，不替代 GUI 交互验收。

旧 dist 便携包保持原状，新包使用明确的独立文件名。当前授权是源码提交与推送，不包含创建 GitHub Release 或上传大二进制；本地产物保留供使用与检查。源码、参数、使用指南、复现脚本和验证文档共同提交。


## GitHub 发布核对

按用户授权直接推送 Lin-Silver/Reverie-Cli 的 main：NVIDIA 源码提交 f09bf57；Computer Use/Harness2/构建与验证记录提交 8dcff3f。git push 成功后，git ls-remote origin refs/heads/main 与本地源码 HEAD 均为 8dcff3f32b3cd4683cf8e80c774720961dd72db5。此发布核对记录随后作为单独文档提交补充，不改变已经验证的内核代码。

未创建 PR、未上传 GitHub Release 二进制。任务清单、活动日志相关的无关修改及既有 rce.md 删除仍留在本地，未包含在这些源码提交中。
