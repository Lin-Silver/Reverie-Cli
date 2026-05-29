use serde::Serialize;

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct ProviderModel {
    pub id: &'static str,
    pub display_name: &'static str,
    pub description: &'static str,
    pub transport: &'static str,
    pub context_length: u32,
    pub output_limit: u32,
    pub supports_vision: bool,
    pub supports_thinking: bool,
    pub provider: &'static str,
}

pub fn nvidia_catalog() -> Vec<ProviderModel> {
    vec![
        ProviderModel {
            id: "moonshotai/kimi-k2.6",
            display_name: "Kimi K2.6",
            description: "Moonshot Kimi K2.6 model on NVIDIA.",
            transport: "request",
            context_length: 262_144,
            output_limit: 98_304,
            supports_vision: false,
            supports_thinking: true,
            provider: "nvidia",
        },
        ProviderModel {
            id: "z-ai/glm-5.1",
            display_name: "GLM 5.1",
            description: "Z.ai GLM-5.1 model on NVIDIA.",
            transport: "openai",
            context_length: 131_072,
            output_limit: 65_536,
            supports_vision: false,
            supports_thinking: true,
            provider: "nvidia",
        },
        ProviderModel {
            id: "deepseek-ai/deepseek-v4-pro",
            display_name: "DeepSeek V4 Pro",
            description: "DeepSeek V4 Pro model on NVIDIA.",
            transport: "openai",
            context_length: 131_072,
            output_limit: 65_536,
            supports_vision: false,
            supports_thinking: true,
            provider: "nvidia",
        },
        ProviderModel {
            id: "minimaxai/minimax-m2.7",
            display_name: "MiniMax M2.7",
            description: "MiniMax M2.7 agentic coding model on NVIDIA.",
            transport: "openai",
            context_length: 204_800,
            output_limit: 65_536,
            supports_vision: false,
            supports_thinking: true,
            provider: "nvidia",
        },
        ProviderModel {
            id: "openai/gpt-oss-120b",
            display_name: "GPT OSS 120B",
            description: "OpenAI GPT OSS 120B on NVIDIA.",
            transport: "openai",
            context_length: 131_072,
            output_limit: 65_536,
            supports_vision: false,
            supports_thinking: true,
            provider: "nvidia",
        },
    ]
}

pub fn modelscope_catalog() -> Vec<ProviderModel> {
    vec![
        ProviderModel {
            id: "ZhipuAI/GLM-5.1",
            display_name: "GLM-5.1",
            description: "Z.ai GLM-5.1 model on ModelScope.",
            transport: "anthropic",
            context_length: 202_752,
            output_limit: 65_536,
            supports_vision: false,
            supports_thinking: true,
            provider: "modelscope",
        },
        ProviderModel {
            id: "deepseek-ai/DeepSeek-V4-Pro",
            display_name: "DeepSeek V4 Pro",
            description: "DeepSeek V4 Pro flagship MoE model on ModelScope.",
            transport: "anthropic",
            context_length: 1_048_576,
            output_limit: 393_216,
            supports_vision: false,
            supports_thinking: true,
            provider: "modelscope",
        },
        ProviderModel {
            id: "moonshotai/Kimi-K2.6",
            display_name: "Kimi K2.6",
            description: "Moonshot Kimi K2.6 multimodal model on ModelScope.",
            transport: "anthropic",
            context_length: 262_144,
            output_limit: 98_304,
            supports_vision: true,
            supports_thinking: true,
            provider: "modelscope",
        },
        ProviderModel {
            id: "Qwen/Qwen3.5-397B-A17B",
            display_name: "Qwen3.5 397B A17B",
            description: "Qwen3.5 397B-A17B model on ModelScope.",
            transport: "anthropic",
            context_length: 262_144,
            output_limit: 65_536,
            supports_vision: true,
            supports_thinking: true,
            provider: "modelscope",
        },
    ]
}

pub fn codex_catalog() -> Vec<ProviderModel> {
    vec![
        ProviderModel {
            id: "gpt-5.5",
            display_name: "GPT-5.5",
            description: "Frontier model for complex coding, research, and real-world work.",
            transport: "codex",
            context_length: 400_000,
            output_limit: 128_000,
            supports_vision: true,
            supports_thinking: true,
            provider: "codex",
        },
        ProviderModel {
            id: "gpt-5.3-codex",
            display_name: "GPT-5.3-Codex",
            description: "Frontier agentic coding model.",
            transport: "codex",
            context_length: 258_400,
            output_limit: 128_000,
            supports_vision: true,
            supports_thinking: true,
            provider: "codex",
        },
        ProviderModel {
            id: "gpt-5.4",
            display_name: "GPT-5.4",
            description: "Frontier agentic coding model.",
            transport: "codex",
            context_length: 400_000,
            output_limit: 128_000,
            supports_vision: true,
            supports_thinking: true,
            provider: "codex",
        },
        ProviderModel {
            id: "gpt-5.4-mini",
            display_name: "GPT-5.4-Mini",
            description: "Smaller frontier agentic coding model.",
            transport: "codex",
            context_length: 258_400,
            output_limit: 128_000,
            supports_vision: true,
            supports_thinking: true,
            provider: "codex",
        },
    ]
}

pub fn gemini_catalog() -> Vec<ProviderModel> {
    vec![
        ProviderModel {
            id: "gemini-2.5-pro",
            display_name: "Gemini 2.5 Pro",
            description: "Google Gemini 2.5 Pro with thinking and tool use.",
            transport: "gemini",
            context_length: 1_048_576,
            output_limit: 65_536,
            supports_vision: true,
            supports_thinking: true,
            provider: "gemini",
        },
        ProviderModel {
            id: "gemini-2.5-flash",
            display_name: "Gemini 2.5 Flash",
            description: "Google Gemini 2.5 Flash — fast reasoning model.",
            transport: "gemini",
            context_length: 1_048_576,
            output_limit: 65_536,
            supports_vision: true,
            supports_thinking: true,
            provider: "gemini",
        },
        ProviderModel {
            id: "gemini-2.0-flash",
            display_name: "Gemini 2.0 Flash",
            description: "Google Gemini 2.0 Flash multimodal model.",
            transport: "gemini",
            context_length: 1_048_576,
            output_limit: 8_192,
            supports_vision: true,
            supports_thinking: false,
            provider: "gemini",
        },
    ]
}

pub fn ollama_catalog() -> Vec<ProviderModel> {
    vec![
        ProviderModel {
            id: "llama3.3",
            display_name: "Llama 3.3 70B",
            description: "Meta Llama 3.3 70B via Ollama local.",
            transport: "ollama",
            context_length: 131_072,
            output_limit: 8_192,
            supports_vision: false,
            supports_thinking: false,
            provider: "ollama",
        },
        ProviderModel {
            id: "qwen3",
            display_name: "Qwen3",
            description: "Qwen3 model via Ollama local.",
            transport: "ollama",
            context_length: 131_072,
            output_limit: 8_192,
            supports_vision: false,
            supports_thinking: true,
            provider: "ollama",
        },
        ProviderModel {
            id: "deepseek-r1",
            display_name: "DeepSeek R1",
            description: "DeepSeek R1 reasoning model via Ollama local.",
            transport: "ollama",
            context_length: 131_072,
            output_limit: 8_192,
            supports_vision: false,
            supports_thinking: true,
            provider: "ollama",
        },
        ProviderModel {
            id: "codestral",
            display_name: "Codestral",
            description: "Mistral Codestral code model via Ollama local.",
            transport: "ollama",
            context_length: 32_768,
            output_limit: 8_192,
            supports_vision: false,
            supports_thinking: false,
            provider: "ollama",
        },
    ]
}

pub fn normalize_reasoning_effort(value: &str) -> &'static str {
    match value.trim().to_ascii_lowercase().as_str() {
        "0" | "minimal" | "min" => "minimal",
        "1" | "low" => "low",
        "3" | "high" => "high",
        "4" | "xhigh" | "x-high" | "extra high" | "extra-high" | "extra_high" => "xhigh",
        _ => "medium",
    }
}

pub fn resolve_model(provider: &str, model_id: &str) -> Option<ProviderModel> {
    let catalog = match provider.trim().to_ascii_lowercase().as_str() {
        "nvidia" => nvidia_catalog(),
        "modelscope" => modelscope_catalog(),
        "codex" => codex_catalog(),
        "gemini" | "google" => gemini_catalog(),
        "ollama" | "local" => ollama_catalog(),
        _ => Vec::new(),
    };
    catalog
        .into_iter()
        .find(|model| model.id.eq_ignore_ascii_case(model_id))
}

pub fn all_provider_names() -> &'static [&'static str] {
    &["nvidia", "modelscope", "codex", "gemini", "ollama"]
}
