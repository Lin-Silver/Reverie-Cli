# 免费模型来源继续核对（2026-10-21）

最初的线索为 Hugging Face 上的 LFM 或 MiniCPM 小模型。前轮[免费接口核对](../2026-10-20-riu-cloud/free-api-search.md)已区分旧免费 Key 公告、当前需要认证的 API 和可匿名访问的演示。 最符合这条记忆的是官方 **MiniCPM5-2B** Space，已实际匿名调用成功。需要标准 Chat 和原生工具的应用另有 OVHcloud 匿名入口；这两种 API 的格式和用途不同。

| 来源 | 实际确认 | 本轮用途与限制 |
| --- | --- | --- |
| [官方 MiniCPM5-2B Hugging Face Space](https://huggingface.co/spaces/openbmb/MiniCPM5-2B-Demo) | 匿名 Gradio/SSE 调用成功 | API 主机为 `https://openbmb-minicpm5-2b-demo.hf.space`；演示没有标准 Chat 的 `tools` 参数，不能计为 RIU 原生工具闭环模型 |
| 官方 LFM2.5-1.2B-Instruct GGUF | 固定版本权重校验通过；本地 llama.cpp 原生函数调用往返通过 | 本地免费运行已获授权；本地 API 是此次启动的服务，不代表找到公共匿名托管 API；尚未通过页面生成质量 |
| OVHcloud AI Endpoints | 官方匿名额度明确；匿名目录 200；GPT-OSS-120B、Qwen3.6-27B 各两次原生工具请求均 200 | 每 IP、每模型每分钟 2 次，无需新密钥；真实 Desktop 开发用例仍有业务或宿主集成失败，不能把协议预检算作完整质量通过 |

OVHcloud 的[官方错误及额度文档](https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-troubleshooting.md)明确区分匿名与认证额度。本轮使用无 Authorization 的匿名请求；没有新建账号、申请密钥、付费、借用其他客户端身份或经未核实网关转发。

已验证的标准 Chat 基址为 `https://oai.endpoints.kepler.ai.cloud.ovh.net/v1`。实时目录位于 `/v1/models`；`gpt-oss-120b`、`Qwen3.6-27B`、`Qwen3.5-397B-A17B`、`Qwen3.8-27B`、`Qwen3.5-9B` 均已完成匿名原生工具往返，响应模型 ID 对应各自请求。后三者的官方 Hugging Face 元数据和 Apache 2.0 许可证也已留档；它们是不同权重模型，不能只按别名重复计数。9B 官方仓库修订为 `c202236235762e1c871ad0ccb60c8ee5ba337b9a`；这份元数据不证明远端服务固定部署了该修订。目录出现或协议预检通过都不等于完整质量验收。模型与消费方式的进度见[实施记录](progress.md)。

GPT-OSS-120B 的官方公开 Hugging Face 元数据也已匿名核对，仓库 `openai/gpt-oss-120b` 为 Apache 2.0，修订 `b5c939de8f754692c1647ca79fbf85e8c1e70f8a`；同样不证明 OVHcloud 固定部署该修订。在 Linux 原生包 `106bbd324fcf60f7` 上的完整开发轮次现已结束：五类生成完整通过 **0/5**，文本 **1/1**。原失败和环境中断保持原样；方案筛选中断前已消耗的两次反馈计入累计预算，续跑剩余为零。五份实际页面另完成模式、主题、错误与键盘复核，查看 22 张代表截图，未改模型 HTML。它未被选入后续正式双模型矩阵；协议往返或目录存在不能代替页面质量。

2026-10-24 的 native8 新候选整组也已完整结束：GPT-OSS 五类生成原始通过 0/5、文本原始通过 0/1；文本实际是正确的 `3 168`，旧数字匹配遗漏 U+202F 空格，原报告保留。五份原生操作与五项独立诊断、35 张实际查看的代表截图将真实模型问题和验证器问题分别记录。新通用修正已在 native9/full14 通过源码与原生消费者检查，当前双模型完整开发十个生成与两个文本已关闭，原始生成 0/10、文本 2/2；不能由协议或包测试推断模型质量。

Qwen3.6-27B 的[官方公开元数据](https://huggingface.co/Qwen/Qwen3.6-27B)现亦已匿名核对：Apache 2.0、未设 gated，仓库修订 `6a9e13bd6fc8f0983b9b99948120bc37f49c13e9`。这不证明 OVHcloud 部署固定修订；原一次计算器开发的主题/状态失败继续保留。当前原生包、full16 观察器校准和新正式 30+6 范围见[当前校准与正式验收](observer-calibration-native9.md)。2026-10-24 15:27 UTC 匿名目录再次返回 200，22 项目录包含所选 397B 与 Qwen3.6；正式调用没有新增密钥或付款。

服务不支持 `cache_prompt` 时，现有定向兼容重试保留工具与历史，仅移除可选缓存提示；新增修复记住当前 agent 已确认的拒绝，避免工具续轮反复产生相同 400。429 按实际 Retry-After 等待；没有通过更换 IP、身份或路径绕过限额。原始 HTTP 错误、SSE、会话、模型 HTML 和截图保留在 `.runtime/riu-completion-20261021`，正式矩阵和开发诊断分开。

在 Desktop 的模型设置中选择标准模型并点击“添加模型”，可按以下字段配置匿名入口；界面和核心的标准模型保存都允许密钥为空。本轮仅在隔离测试配置中使用，没有更改用户默认来源。

| 字段 | 值 |
| --- | --- |
| 模型 ID | `Qwen3.5-9B`，或实时目录中的其他实际 ID |
| 显示名称 | 自选，例如 `OVH Qwen3.5-9B` |
| 提供者 | `OpenAI Chat Completions` |
| 基础 URL | `https://oai.endpoints.kepler.ai.cloud.ovh.net/v1` |
| 请求路径 | `/chat/completions` |
| API 密钥 | 留空 |

标准 Chat 的调用形式如下，不需要 Authorization。短文本请求和原生工具协议可用性分别验证，不能据此认定生成页面合格；9B 的五类开发任务实际均未通过，文本对照通过。

```bash
curl -N 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions' \
  -H 'Content-Type: application/json' \
  --data-binary '{"model":"Qwen3.5-9B","messages":[{"role":"user","content":"你好"}],"stream":true}'
```

MiniCPM5-2B 的公开 Gradio 调用形式和旧 MiniCPM-V 4.6 免费 Key 公告，另见[原始接口核对](../2026-10-20-riu-cloud/free-api-search.md)。它的 Space 地址用于 Gradio 客户端，标准模型字段中的基础 URL 则需要兼容上述 Chat 协议。
