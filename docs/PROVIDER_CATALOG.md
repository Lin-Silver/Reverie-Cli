# Provider model catalogs

For AIhubMix, Agnes, SenseNova, ModelScope, NVIDIA, OpenCode and custom providers,
the last successful `/models` response is the authoritative inventory for that
connection. A successful refresh replaces the entire previous list, including
when the new list is empty. Failed requests and malformed responses retain the
last successful inventory. Built-in catalogs are fallbacks only when no successful
inventory exists for the current endpoint and credential.

The inventory is saved in provider configuration under `model_catalog`. Its
connection key hashes the normalized catalog URL and credential; custom providers
also include their API format. Changing the endpoint or credential prevents reuse
of another connection's saved inventory. Credentials are not stored in this key.
Custom model context limits entered by the user still override API context limits.

Desktop refresh and provider availability probes save successful inventories.
Ordinary desktop reads and model selections reuse them without refreshing over
the network. If a selected model disappears from a successful inventory, the
source uses an available model from that inventory; an empty inventory has no
usable runtime model. A newly added custom provider still requires a model choice.
Codex retains its own discovery mechanism. The Gemini source and compatible
Gemini providers list models through the Google Gen AI SDK.
OpenCode and Agnes can load their initial live catalogs when a key is configured.
Those initial inventories are saved as well. OpenCode's built-in setting only
applies before the first successful refresh; it never overrides an already
successful API inventory. Agnes classifies live chat models by their declared
output modalities rather than requiring a legacy model-name prefix.

## SenseNova Messages API

SenseNova inference uses the Anthropic-compatible Messages API for all chat
models, including the Flash Lite model. The SDK receives the root URL
`https://token.sensenova.cn` and sends `POST /v1/messages` with Bearer authentication.
Existing root, `/v1` and `/v1/chat/completions` settings normalize to that root.
Model discovery continues to use `GET /v1/models`.

Messages use native Anthropic content blocks and tool schemas. Tool replies are
sent as `tool_result` blocks; signed thinking blocks are preserved for subsequent
turns. The non-thinking choice sends `thinking.type=disabled`. Models exposing an
effort control use `thinking.type=adaptive` with `output_config.effort`; other
reasoning models retain provider-managed defaults. OpenAI-only sampling fields
are not added to Messages requests.
Kimi K3 requires temperature `1`, so its saved configuration and request use
that value. GLM-5.3 rejects explicitly disabling thinking; its requests retain
the provider's thinking defaults even if the source previously selected an
off mode for another model.
SenseNova currently emits `content: null` in the initial streaming message. The
SenseNova stream adapter normalizes that initial value to `[]` before the SDK
accumulates content blocks, preserving the remaining events and SDK lifecycle.

The updated built-in chat fallback contains `deepseek-v4-flash`, `deepseek-flash`,
`glm-5.2`, `glm-5.3`, `kimi-k3`, `sensenova-6.8-flash-lite` and `sensenova-6.8-flash`.
Image-output models stay out of the chat selector. The live list always takes
precedence over these fallback IDs and metadata.

Official compatibility reference:
[SenseNova Skills FAQ](https://github.com/OpenSenseNova/SenseNova-Skills/blob/main/docs/faq_CN.md).
