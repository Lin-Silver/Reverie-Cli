# NVIDIA offline catalog

Refreshed on 2026-10-23. This is a curated catalog for general assistance, coding, and tool use. The CLI and desktop obtain the same bundled list from `reverie/nvidia.py`; opening it does not require an inventory request.

## Current models

| Hosted model ID | Context tokens | Thinking controls | Default output budget |
| --- | ---: | --- | ---: |
| `meta/muse-glimmer-30b` | 131,072 | none / minimal / low / medium / high / max | 16,384 |
| `minimaxai/minimax-m3.1-flash` | 262,144 | low / medium / high / xhigh / max | 65,536 |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 1,048,576 | on / off | 16,384 |
| `nvidia/nemotron-3-super-120b-a12b` | 1,000,000 | none / low / high | Full remaining context |
| `nvidia/nemotron-3-ultra-550b-a55b` | 1,000,000 | Fixed reasoning | 16,384 |
| `poolside/laguna-xs-2.1` | 262,000 | None | 8,192 |
| `nvidia/nemotron-3.5-super-vl-120b-a12b` | 262,144 | none / low / high | 16,384 |
| `deepseek-ai/deepseek-v4.1-flash` | 1,048,576 | Provider default | 262,144 |
| `z-ai/glm-5.3-flash` | 1,048,576 | low / high / max | 16,384 |
| `stepfun-ai/step-5-preview` | 1,048,576 | Fixed reasoning | 4,096 |
| `openai/gpt-oss-20b` | 131,072 | low / medium / high | 4,096 |

Generation budgets include reasoning where the provider counts it. Reverie reserves space for the prompt and tools before sending requests. These budgets are upper bounds, not a requirement to generate that many tokens.

## Model-specific sampling

Sampling was checked against publishers' Hugging Face model cards, generation configurations, and NVIDIA API references on 2026-10-23, rather than copying Build playground slider values where a model-specific recommendation is documented. These are author-recommended defaults for general/agentic use, not a claim that a single preset is optimal for every task. Only the NVIDIA source uses these profiles.

| Hosted model | Temperature | Top-p | Additional sampling | Official source |
| --- | ---: | ---: | --- | --- |
| Muse Glimmer 30B | 1.0 | 0.95 | `top_k=64` | [Meta best practices](https://huggingface.co/meta-models/Muse-Glimmer-30B#best-practices) |
| MiniMax M3.1 Flash | 1.0 | 0.95 | `chat_template_kwargs.reasoning_effort` | [NVIDIA inference reference](https://docs.api.nvidia.com/nim/reference/minimaxai-minimax-m3-1-flash-infer) |
| Nemotron 3.5 Lightning | 1.0 | 0.95 | Provider defaults | [NVIDIA model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16) |
| Nemotron 3 Super | 1.0 | 0.95 | Provider defaults | [NVIDIA model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16) |
| Nemotron 3 Ultra | 1.0 | 0.95 | Provider defaults | [NVIDIA generation config](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16/blob/main/generation_config.json) |
| Laguna XS 2.1 | 1.0 | 1.0 | `top_k=20`, `min_p=0.0` | [Poolside model card/config](https://huggingface.co/poolside/Laguna-XS-2.1/blob/main/generation_config.json) |
| Nemotron 3.5 Super VL | Text: 1.0; image/video: 0.6 | 0.95 | Automatic input-dependent temperature | [NVIDIA model summary](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16#model-summary) |
| DeepSeek V4.1 Flash | 1.0 | 0.95 | Provider defaults | [DeepSeek recommended sampling](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash#minimal-inference) |
| GLM 5.3 Flash | 1.0 | 0.95 | Provider defaults | [Z.ai generation config](https://huggingface.co/zai-org/GLM-5.3-Flash/blob/main/generation_config.json) |
| Step 5 Preview | 1.0 | 0.95 | `top_k=0` (disabled) | [StepFun evaluation notes](https://huggingface.co/stepfun-ai/Step-5-Preview#evaluation-notes) |
| GPT-OSS-20B | 1.0 | 1.0 | Provider defaults | [OpenAI recommended sampling](https://github.com/openai/gpt-oss#recommended-sampling-parameters) |

DeepSeek also permits top-p 1.0; the profile retains 0.95, matching its agentic evaluations. GLM publishes different benchmark-specific presets; its bundled general-purpose profile follows the publisher's `generation_config.json`, not a single benchmark harness. For Super VL, any image/video content still present in the outgoing conversation selects temperature 0.6, including earlier turns; a text-only request selects 1.0. This is applied consistently to streaming, non-streaming, and SDK fallback requests.

The CLI/desktop attachment gate follows the NVIDIA model's declared visual capability, rather than rejecting every SDK transport. This allows a Super VL image attachment to reach the actual request and activate its visual sampling profile; text-only NVIDIA models remain blocked.

Legacy shared `nvidia.temperature`, `top_p`, `top_k`, and penalty fields do not override these model-owned defaults. Parameters without a publisher recommendation are left to the hosted provider instead of inventing penalties or a shared top-k. Output budgets and thinking controls remain separately configured. Top-k/min-p extensions use SDK `extra_body` (Muse/Laguna) or the direct JSON body (Step), rather than unsupported OpenAI SDK keyword arguments.

As requested, the NVIDIA settings page no longer exposes the ineffective shared temperature/top-p inputs. Other sources retain their existing sampling controls. Legacy saved fields are preserved for compatibility but do not override the dedicated NVIDIA profiles.

A successful HTTP response establishes request compatibility, not proof that the hosted backend honors every undocumented extension or that these defaults maximize task quality.

## Hosted request profiles

Models with dedicated request profiles:

- [MiniMax M3.1 Flash](https://build.nvidia.com/minimaxai/minimax-m3.1-flash): text, image, and video input; SDK transport; temperature 1.0 and top-p 0.95. Its reasoning level is sent through `chat_template_kwargs.reasoning_effort`, and prior assistant reasoning is preserved for tool follow-ups. NVIDIA's hosted catalog advertises 262K context and the inference reference caps output at 65,536 tokens; the model card describes up to 1M depending on serving configuration.
- [Nemotron 3.5 Super VL](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b): text, image, and video input; SDK transport; native `reasoning_effort`. The hosted Build page advertises 262K context, while the architecture card describes up to 1M depending on deployment. The bundled value uses the hosted page's smaller window. Its [inference reference](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-super-vl-120b-a12b-infer) caps generated output at 131,072 tokens.
- [DeepSeek V4.1 Flash](https://build.nvidia.com/deepseek-ai/deepseek-v4.1-flash): text and image input; SDK transport; temperature 1.0 and top-p 0.95. The default budget follows the official 262,144-token example, as requested. The hosted example and inference schema do not expose the old V4 `thinking` / string `reasoning_effort` template configuration, so those fields are omitted.
- [GLM 5.3 Flash](https://docs.api.nvidia.com/nim/reference/z-ai-glm-5-3-flash): text and image input; SDK transport; native `reasoning_effort`, with `chat_template_kwargs.clear_thinking=true`. Sampling follows the publisher's generation config: temperature 1.0 and top-p 0.95.
- [Step 5 Preview](https://docs.api.nvidia.com/nim/reference/stepfun-ai-step-5-preview-infer): text and image input; request transport; publisher-recommended temperature 1.0, top-p 0.95, and disabled top-k; fixed reasoning. Assistant `reasoning_content` is retained when continuing a tool conversation. Video and audio are not advertised as supported inputs.
- [GPT-OSS-20B](https://docs.api.nvidia.com/nim/reference/openai-gpt-oss-20b-infer): text input; SDK transport; temperature 1.0 and top-p 1.0. Output is capped at the documented hosted limit of 4,096 tokens, rather than using the context window as an output budget.

GLM-5.3's non-Flash endpoint is marked for deprecation on NVIDIA's model catalog, so `z-ai/glm-5.3` is excluded from the built-in list. GLM-5.3 Flash is a separate endpoint and remains listed while NVIDIA continues to mark it available. Kimi K2.6 still appears in `/v1/models`, but an authenticated inference request returned HTTP 404; inventory presence alone does not establish availability.

DeepSeek V4.1 Flash and GLM 5.3 Flash remain selectable, as requested, with this note in both the CLI and desktop model descriptions: “NVIDIA 可能尚未针对该模型进行多并发调用优化；本次验证多次超时。” The concurrency explanation is a possibility, not a confirmed diagnosis. The observed result is repeated request timeouts.

## Removed endpoints

All six endpoints returned authenticated HTTP 410 with an explicit end-of-life message on 2026-10-16:

| Model ID | Provider-reported end of life, UTC |
| --- | --- |
| `deepseek-ai/deepseek-v4-flash-0731` | 2026-09-21 08:00 |
| `deepseek-ai/deepseek-v4-pro-0813` | 2026-09-14 08:00 |
| `moonshotai/kimi-k3` | 2026-10-15 08:00 |
| `minimaxai/minimax-m3` | 2026-09-09 09:00 |
| `stepfun-ai/step-3.7-flash` | 2026-08-28 08:00 |
| `openai/gpt-oss-120b` | 2026-09-03 08:00 |

Saved configurations containing an unavailable model fall back to the existing Muse Glimmer default.

## Sampling refinement verification

- Python: 549 tests passed; desktop type checking and production build passed.
- The rebuilt desktop kernel and standalone CLI each passed 10 local HTTP serialization checks across the nine SDK models, including Super VL text/image temperature switching. Both expose only the four remaining NVIDIA connection/reasoning fields, without shared temperature/top-p inputs. Step's raw adapter is bound to the official API URL and was checked separately through authenticated requests.
- The latest standalone CLI completed a real Super VL text prompt with output `OK`. Its Step 5 prompt exceeded the 75-second process limit; the cause is not established. Step's source-agent request preparation and authenticated two-turn tool conversation passed with the new sampling values, preserving assistant reasoning and returning `5017`.
- The latest desktop kernel accepted a real image attachment through its SDK bridge and identified the red test image as `Red` using Super VL's visual profile. Video and maximum-length/quality benchmarking were not exercised.
- DeepSeek V4.1, GLM 5.3 Flash, Nemotron 3 Ultra, and Lightning timed out in bounded source checks. Laguna returned HTTP 503 with an explicit worker request-limit error. These availability results are recorded separately from sampling configuration correctness; the checks were serial and do not establish a local concurrency fault.
- A headless production-renderer check with a real source bridge confirms that NVIDIA has no shared temperature/top-p controls while OpenCode retains its temperature control. Native Electron window APIs were stubbed for that UI check; the independent frozen attachment/inference check used the actual desktop kernel. No installed GUI release or installer was replaced.

## Verification

- Python: 444 tests passed across the NVIDIA, agent, desktop bridge, configuration, transport, batch prompt, cancellation, SubAgent, and adjacent built-in provider tests.
- Desktop: type checking passed; all 104 application interaction tests passed.
- The source bridge, rebuilt standalone CLI, and rebuilt desktop kernel each return the same 10 models, preserve the two concurrency notes, and save DeepSeek's 262,144-token default budget.
- Authenticated streaming tool-call / tool-result / final-answer checks passed for Muse Glimmer, Nemotron 3 Super, Nemotron 3.5 Super VL, Laguna XS, Step 5 Preview, and GPT-OSS-20B. Nemotron 3.5 Lightning completed an authenticated text request after a tool follow-up timed out.
- Step 5 Preview, Nemotron 3.5 Super VL, and Muse Glimmer correctly identified a locally generated red image. Video input and advertised maximum context/output sizes were not exhaustively exercised.
- DeepSeek V4.1 Flash, GLM 5.3 Flash, and the existing Nemotron 3 Ultra endpoint timed out. Their live availability is not confirmed by the catalog update.
- The rebuilt standalone CLI completed real Step 5 Preview and Nemotron 3.5 Super VL prompts with `success=true` and output `OK`. Step 5's existing prompt-cache compatibility retry was exercised successfully.
- The production renderer was checked with a real source SDK bridge in headless Chromium at 1200px and 900px widths. Both notes remain readable without clipping or browser errors. Native Electron window controls were stubbed for that visual check; an installed GUI release/installer was not replaced.

The checked local NVIDIA configuration selects Step 5 Preview, uses the official `/v1/chat/completions` endpoint, has 1,048,576 context tokens and an 8,192-token output budget, and retains the configured API key. The actual timeout is 60 seconds: the stored legacy value of 300 seconds follows the global 60-second setting. The active source remains OpenCode.
