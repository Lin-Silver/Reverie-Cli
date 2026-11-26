# Auto Check 原生迁移记录

## 2026-11-26 四档权限

当前会话和工作区默认设置均提供 Strict、Normal、Auto、Full Access。终端可用 `/permission strict|normal|auto|full_access` 切换，`/permission fallback wait|deny` 设置 Auto 的人工回退方式。旧配置中的 `default` 对应 Normal，`auto_check` 对应 Auto。

Strict 向人工提交每种工具的首次未授权调用。Normal 在终端命令上使用同一审批流程，其他已经可用、受信任的工具直接运行。Full Access 免交互审批。显式只读、插件信任、工具本身的命令策略及审计各自生效。对远端 MCP，宿主依据已信任服务的只读与破坏性注解判断其声明的能力；服务器自身的实现不在本地文件权限控制内。

会话和项目授权同时绑定登记项目和实际执行工作区。全局授权跨项目。终端授权绑定完整命令和参数对象，普通工具绑定工具身份，MCP 另绑定服务配置和工具声明。授权存于应用数据的 `.reverie/security/approval-grants.sqlite3`。一次批准仅交付当前调用。

Auto 将可审查工具分批提交，逐调用按 ID 取回结果。模型返回明确拒绝、风险达到阈值、审查失败时，`deny` 直接拒绝此次调用，即使以前记住过此工具。`wait` 使用已有人工授权，缺少授权时排队，独立调用和后续模型轮次仍可推进。停止后尚未交付的调用记录为 `not_started`；中断前已开始交付但缺少结果的记录为 `unknown`，恢复时不重放。旧配置的 `fail_open` 和 `strict_allow_read_only` 不会放宽四档规则。

以下为此前独立模块的迁移和验证记录。

## 来源

Python 归档：`Reverie-Cli-py`，提交 `070fa25b07692c90c56a6b00a9a969ff2abb7804`。

| 文件 | Git blob |
|---|---|
| `ReverieCli-py/reverie/security_policy.py` | `e5ccab9bc53a793e65b4e9d33a5cd0482427ac70` |
| `ReverieCli-py/reverie/agent/permission_review.py` | `acbceea6d47b7a1ac6ad442398d4190988a56fb9` |
| `ReverieCli-py/reverie/agent/permission_reviewer.py` | `34e28e14d5328d94d06721c79802046af48c2950` |
| `ReverieCli-py/reverie/agent/tool_executor.py` | `8425433bbab47335282c0d419716493d2470e86b` |
| `ReverieCli-py/tests/test_permission_modes.py` | `6d56b66b18090283d7c6c328fc059ea279051978` |

固定 `REVIEW_SYSTEM_PROMPT` 与上述 Python 源码文本逐字核对，通过 CRLF→LF 归一化后的 SHA-256 为 `75711381eee54e7812d0e98800119ae7a70848ffa2776ae7537bd5698fcc00f7`。来源身份和本轮检查保存在 `.runtime/rust-3.0/approval-unit/source-identity.json`，不作为发布资产上传。

## 已实现

- `approval_review.rs` 提供配置归一化、可信工具元数据的静态先验、无历史批次请求、follow/custom 模型选择、结果解析、失败先验及审批判断。
- 默认配置保留 `follow`、45 秒、900 tokens、`medium`、`fail_open=false`、`review_read_only=false`。
- 请求最多提交 24 项；字符串最多初始 4,000 字符，容器最多 40 项，递归预算减半。跳过的只读调用不发给审查模型；超过批次上限的调用保留原先验并标为 `missing`。
- 每调用风险决定是否询问；`batch_risk` 只能提高汇总风险，不能提高全部调用的风险。
- `ResponsePolicy` 显式区分 Python 的按 ID/位置兼容解析和严格 ID 绑定；`HardDenialPolicy` 显式区分人工批准例外与硬拒绝，两者均没有模块默认策略。主会话必须依据用户决定选择。
- `fail_open` 只作用于失败审查，不能抬起硬政策或取消。组件调用不能凭自称用户手势或普通会话批准跳过 Host 审批。
- 自定义审查模型优先按名称查找，名称缺失时保留历史 `model_index` 回退；不可用时跟随正在执行的主模型并返回提示。非标准来源仅接收 Host 已解析的目标，不能宣称该来源目录已完成迁移。
- transport 模型保留凭据；审查消息只含固定 system 和当前工具批次。请求覆盖温度、输出预算、非流式和超时配置，Host 仍需对整次调用执行超时与取消。
- `rust-approval-smoke.mjs` 使用本地模型替身和真实 SDK、原生文件工具，验证授权效果、拒绝与自定义回复、会话范围、失败、取消、超时及绑定策略。

## 本轮基础验证

`rustfmt --edition 2024 ReverieCli-rs/crates/core/src/approval_review.rs` 与 `node --check scripts/verification/rust-approval-smoke.mjs` 通过。

主会话注册模块后，已用锁文件工作区执行：

```powershell
cargo test --manifest-path ReverieCli-rs/Cargo.toml --locked --offline -p reverie-core --lib approval_review
cargo clippy --manifest-path ReverieCli-rs/Cargo.toml --locked --offline -p reverie-core --all-targets -- -D warnings
```

结果：**19 passed，0 failed，56 filtered out**；Clippy 以 `-D warnings` 通过。独立模块测试此前也通过 19 项，本记录采用注册后的工作区结果。

实际 SDK 脚本的策略预期由执行者显式传入，不自行冻结用户尚未决定的行为：

```text
node scripts/verification/rust-approval-smoke.mjs <reverie binary> <artifact directory>
```

截至本记录首次编写时，实际 SDK 验证等待 Host 整合，不能把脚本存在或 Node 语法通过表述为运行通过。

## 独立模块首次交接时的未验证项

1. 完成 Host 整合后的 debug/release 实际 SDK 运行和二进制身份核对。
2. 真实外部模型的风险判断、提示注入识别与误报率；本地替身只验证协议和执行链。
3. 真实 OpenAI/Responses、Anthropic、Gemini 和自定义 HTTP 服务的审查调用及错误恢复。
4. GUI/TUI 的 Auto Check 配置、风险展示、once/session/deny/message 交互及输入法行为。
5. 真实 MCP/插件组件、view call 与升级后权限变化的审查及人工审批。
6. 真实网络故障、系统代理、长任务、进程退出与取消竞争下的恢复。
7. macOS arm64/x64 和 Linux 原生包中的 Auto Check 完整运行。
8. 两小时 AiO、长期会话及大批次审查的真实模型稳定性与成本。
