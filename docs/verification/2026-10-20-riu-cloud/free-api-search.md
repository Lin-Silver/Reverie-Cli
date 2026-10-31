# Hugging Face 小模型免费 API 核对

核对时间：2026-10-21 UTC。仅使用官方模型页、Space 源码/API 文档和一次匿名公开推理请求；未注册账户、申请密钥或购买额度。

用户记忆最接近 **MiniCPM-V 4.6**：其[官方 Hugging Face 页面](https://huggingface.co/openbmb/MiniCPM-V-4.6)仍保留 2026-05-17 发布公开免费 API Key 的公告。当前链接到的[官方 API 文档](https://github.com/OpenBMB/MiniCPM-V/blob/main/docs/api.md)已经要求在 platform.modelbest.cn 创建 Key，Base URL 为 `https://api.modelbest.cn/v1`。本轮匿名 GET `/models` 实际返回 401 `invalid_api_key`；这证明当前入口要求认证，不能从旧公告推断今天仍可免 Key 调用。没有使用第三方分叉中保留的旧 Key。

本轮另找到并实测可用的 **[OpenBMB MiniCPM5-2B 官方 Space](https://huggingface.co/spaces/openbmb/MiniCPM5-2B-Demo)**：

- API 主机：`https://openbmb-minicpm5-2b-demo.hf.space`。
- 公开接口：`POST /gradio_api/call/v2/predict`，随后 GET `/gradio_api/call/predict/{event_id}` 接收 SSE。
- 未带 Authorization、Cookie 或 HF Token，POST 与 SSE 均为 HTTP 200；一次 `2+2` 请求在约 3.900s 内完整结束，最终答案为 4。原始推理文本、特殊标记与流数据完整保存；此探针只证明可用性，不是 RIU 质量或延迟基准。
- Space API 公开参数为 `message`、`history`、`thinking_mode`、`temperature`、`top_p`；没有暴露 OpenAI `tools` / `tool_choice`。因此未将它直接接入现有标准 Chat 工具执行矩阵，也未用文本解析伪造原生工具调用。此限制针对该 Space 接口，不推断模型本身不支持工具。
- 这是共享 ZeroGPU Demo，受配额和排队限制。[Hugging Face 当前官方说明](https://huggingface.co/docs/hub/spaces-zerogpu#usage-tiers)列出匿名用户每日 2 分钟 GPU 配额；不能当成无限量生产 API。

Space 自己的 API 描述提供以下 Python 调用形式（需要 `gradio_client`）：

```python
from gradio_client import Client

client = Client("openbmb/MiniCPM5-2B-Demo")
result = client.predict(message="你好", api_name="/predict")
print(result)
```

本轮实际验证的是上述公开 HTTP/SSE 接口；Python 形式来自 Space 自动生成的调用示例，未另发一次重复推理请求。

LFM 方面，[Liquid AI 官方 FAQ](https://www.liquid.ai/faq)当前说明不提供自有托管 API，免费 playground 与其他提供者另有条件。官方 LFM2-MCP Space 的说明是浏览器内 Transformers.js/WebGPU 工具调用；它不等于公开的远程模型推理 API。本轮查到的 LFM2.5-8B-A1B Gradio Space 处于 PAUSED，未把模型公开下载或 WebGPU 页面误记为可用免费远程 API。

原始证据在 `final-evidence.zip` 内的 `.runtime/riu-cloud-20261020/hf-free-api-search-20261021/`，包括官方文档、Space 源码/接口定义、401 返回、匿名请求、完整 SSE 和带时间戳的探针审计。
