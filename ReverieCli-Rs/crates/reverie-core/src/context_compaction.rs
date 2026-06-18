//! Context compaction strategies for managing large conversation histories.
//!
//! This module provides various strategies for reducing context size while
//! preserving important information for LLM conversations.

use crate::session::SessionMessage;
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Compaction strategy to use
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Default)]
pub enum CompactionStrategy {
    /// Keep only the most recent messages
    #[default]
    SlidingWindow,
    /// Summarize older messages
    Summary,
    /// Keep messages based on importance scoring
    ImportanceBased,
    /// Adaptive strategy that chooses based on context size
    Adaptive,
}

/// Configuration for context compaction
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompactionConfig {
    /// Strategy to use
    pub strategy: CompactionStrategy,
    /// Maximum number of messages to keep
    pub max_messages: usize,
    /// Maximum tokens to keep
    pub max_tokens: Option<usize>,
    /// Number of messages to keep at the start (system prompt)
    pub keep_start: usize,
    /// Number of messages to keep at the end (recent context)
    pub keep_end: usize,
    /// Whether to summarize messages
    pub summarize: bool,
    /// Importance threshold for importance-based strategy
    pub importance_threshold: f64,
}

impl Default for CompactionConfig {
    fn default() -> Self {
        Self {
            strategy: CompactionStrategy::SlidingWindow,
            max_messages: 100,
            max_tokens: None,
            keep_start: 2,
            keep_end: 10,
            summarize: true,
            importance_threshold: 0.5,
        }
    }
}

/// Build a `CompactionConfig` from the `extra` map in `Config`.
///
/// Recognised keys (all optional):
/// - `compaction_enabled` (bool, default true)
/// - `compaction_strategy` (string: sliding_window | summary | importance | adaptive)
/// - `compaction_max_messages` (u64)
/// - `compaction_max_tokens` (u64)
/// - `compaction_keep_start` (u64)
/// - `compaction_keep_end` (u64)
pub fn compaction_config_from_extras(
    extras: &std::collections::BTreeMap<String, Value>,
) -> Option<CompactionConfig> {
    let enabled = extras
        .get("compaction_enabled")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    if !enabled {
        return None;
    }

    let strategy = extras
        .get("compaction_strategy")
        .and_then(Value::as_str)
        .map(|s| match s.trim().to_ascii_lowercase().as_str() {
            "summary" => CompactionStrategy::Summary,
            "importance" | "importance_based" => CompactionStrategy::ImportanceBased,
            "adaptive" => CompactionStrategy::Adaptive,
            _ => CompactionStrategy::SlidingWindow,
        })
        .unwrap_or_default();

    let max_messages = extras
        .get("compaction_max_messages")
        .and_then(Value::as_u64)
        .map(|v| v as usize)
        .unwrap_or(100);

    let max_tokens = extras
        .get("compaction_max_tokens")
        .and_then(Value::as_u64)
        .map(|v| v as usize);

    let keep_start = extras
        .get("compaction_keep_start")
        .and_then(Value::as_u64)
        .map(|v| v as usize)
        .unwrap_or(2);

    let keep_end = extras
        .get("compaction_keep_end")
        .and_then(Value::as_u64)
        .map(|v| v as usize)
        .unwrap_or(10);

    Some(CompactionConfig {
        strategy,
        max_messages,
        max_tokens,
        keep_start,
        keep_end,
        ..Default::default()
    })
}

/// Compact a list of `SessionMessage`s according to the given config.
///
/// Guarantees:
/// - System messages at the start are always preserved (`keep_start`).
/// - Recent messages are always preserved (`keep_end`).
/// - Tool-call assistant messages and their matching tool-result messages
///   are never separated: if one is kept, the other is too.
/// - When `max_tokens` is set, token estimation is used to further trim.
pub fn compact_session_messages(
    messages: &[SessionMessage],
    config: &CompactionConfig,
) -> Vec<SessionMessage> {
    if messages.len() <= config.max_messages {
        if let Some(max_tok) = config.max_tokens {
            let total = estimate_session_tokens(messages);
            if total <= max_tok {
                return messages.to_vec();
            }
        } else {
            return messages.to_vec();
        }
    }

    // Select strategy
    let effective_strategy = if config.strategy == CompactionStrategy::Adaptive {
        let total_tokens = estimate_session_tokens(messages);
        if total_tokens < 4000 {
            CompactionStrategy::SlidingWindow
        } else if total_tokens < 16000 {
            CompactionStrategy::Summary
        } else {
            CompactionStrategy::ImportanceBased
        }
    } else {
        config.strategy
    };

    match effective_strategy {
        CompactionStrategy::SlidingWindow | CompactionStrategy::Adaptive => {
            compact_sliding(messages, config)
        }
        CompactionStrategy::Summary => compact_with_summary(messages, config),
        CompactionStrategy::ImportanceBased => compact_importance(messages, config),
    }
}

/// Sliding-window compaction: keep `keep_start` from the front and
/// `keep_end` from the back, ensuring tool-call pairs stay intact.
fn compact_sliding(messages: &[SessionMessage], config: &CompactionConfig) -> Vec<SessionMessage> {
    let n = messages.len();
    let keep_start = config.keep_start.min(n);
    let keep_end = config.keep_end.min(n.saturating_sub(keep_start));
    let cut_start = keep_start;
    let cut_end = n.saturating_sub(keep_end);

    if cut_start >= cut_end {
        return messages.to_vec();
    }

    let mut kept = Vec::with_capacity(keep_start + keep_end + 4);
    kept.extend_from_slice(&messages[..cut_start]);
    // Ensure the tail doesn't start with an orphaned tool result
    let adjusted = repair_tool_pair_boundary(messages, cut_end);
    kept.extend_from_slice(&messages[adjusted..]);

    apply_token_limit(kept, config)
}

/// Summary compaction: keep start/end, replace middle with a deterministic
/// summary message.
fn compact_with_summary(
    messages: &[SessionMessage],
    config: &CompactionConfig,
) -> Vec<SessionMessage> {
    let n = messages.len();
    let keep_start = config.keep_start.min(n);
    let keep_end = config.keep_end.min(n.saturating_sub(keep_start));
    let cut_start = keep_start;
    let cut_end = n.saturating_sub(keep_end);

    if cut_start >= cut_end {
        return messages.to_vec();
    }

    let middle = &messages[cut_start..cut_end];
    let summary_text = build_session_summary(middle);

    let mut kept = Vec::with_capacity(keep_start + 1 + keep_end);
    kept.extend_from_slice(&messages[..cut_start]);
    if !summary_text.is_empty() {
        kept.push(SessionMessage::new(
            "system",
            serde_json::json!(summary_text),
        ));
    }
    let adjusted = repair_tool_pair_boundary(messages, cut_end);
    kept.extend_from_slice(&messages[adjusted..]);

    apply_token_limit(kept, config)
}

/// Importance-based compaction: score each message, keep the top N,
/// preserving original order and tool-call pairs.
fn compact_importance(
    messages: &[SessionMessage],
    config: &CompactionConfig,
) -> Vec<SessionMessage> {
    let n = messages.len();
    let mut scores: Vec<(usize, f64)> = messages
        .iter()
        .enumerate()
        .map(|(i, m)| (i, score_session_message(m, i, n)))
        .collect();

    // Always keep system messages, tool-call pairs, and the last keep_end
    let keep_start = config.keep_start.min(n);
    let keep_end_start = n.saturating_sub(config.keep_end);
    for (i, score) in &mut scores {
        if *i < keep_start || *i >= keep_end_start {
            *score = 2.0; // force keep
        }
    }

    scores.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    let keep_count = config.max_messages.min(n);
    let mut kept_indices: Vec<usize> = scores.iter().take(keep_count).map(|(i, _)| *i).collect();
    kept_indices.sort_unstable();

    // Repair tool-call pairs: if an assistant with tool_calls is kept, its
    // subsequent tool results must be kept too, and vice versa.
    let kept_set: std::collections::HashSet<usize> = kept_indices.iter().copied().collect();
    let mut final_indices = kept_set;
    for &idx in &kept_indices {
        repair_tool_pair_indices(messages, idx, &mut final_indices);
    }

    let mut final_sorted: Vec<usize> = final_indices.into_iter().collect();
    final_sorted.sort_unstable();

    let kept: Vec<SessionMessage> = final_sorted
        .into_iter()
        .map(|i| messages[i].clone())
        .collect();

    apply_token_limit(kept, config)
}

/// Ensure that if the tail starts with a tool result whose matching
/// assistant is in the cut zone, we walk backward to include the
/// assistant + all its tool results.
fn repair_tool_pair_boundary(messages: &[SessionMessage], mut boundary: usize) -> usize {
    while boundary > 0 && boundary < messages.len() {
        if messages[boundary].role == "tool" {
            boundary -= 1;
        } else {
            break;
        }
    }
    boundary
}

/// Ensure tool_call assistant and all its tool results stay together.
fn repair_tool_pair_indices(
    messages: &[SessionMessage],
    idx: usize,
    kept: &mut std::collections::HashSet<usize>,
) {
    let msg = &messages[idx];
    // If this is an assistant with tool_calls, include subsequent tool results
    if msg.role == "assistant" && !msg.tool_calls.is_empty() {
        let mut j = idx + 1;
        while j < messages.len() && messages[j].role == "tool" {
            kept.insert(j);
            j += 1;
        }
    }
    // If this is a tool result, include the preceding assistant
    if msg.role == "tool" {
        let mut j = idx;
        while j > 0 {
            j -= 1;
            if messages[j].role == "assistant" && !messages[j].tool_calls.is_empty() {
                kept.insert(j);
                // Also include any other tool results between assistant and idx
                for (k, msg_k) in messages.iter().enumerate().take(idx).skip(j + 1) {
                    if msg_k.role == "tool" {
                        kept.insert(k);
                    }
                }
                break;
            }
            if messages[j].role != "tool" {
                break;
            }
        }
    }
}

fn score_session_message(msg: &SessionMessage, index: usize, total: usize) -> f64 {
    let mut score = 0.5;
    // Recency
    let recency = index as f64 / total.max(1) as f64;
    score += recency * 0.3;
    // System messages
    if msg.role == "system" {
        score += 0.2;
    }
    // Tool calls/results
    if !msg.tool_calls.is_empty() || msg.tool_call_id.is_some() {
        score += 0.15;
    }
    // Code content
    let text = content_to_string(&msg.content);
    if text.contains("```") || text.contains("fn ") || text.contains("class ") {
        score += 0.1;
    }
    score.min(1.0)
}

fn content_to_string(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        _ => value.to_string(),
    }
}

fn estimate_session_tokens(messages: &[SessionMessage]) -> usize {
    messages
        .iter()
        .map(|m| {
            let text = content_to_string(&m.content);
            estimate_tokens_in_string(&text)
        })
        .sum()
}

fn apply_token_limit(
    messages: Vec<SessionMessage>,
    config: &CompactionConfig,
) -> Vec<SessionMessage> {
    let Some(max_tok) = config.max_tokens else {
        return messages;
    };
    let total = estimate_session_tokens(&messages);
    if total <= max_tok {
        return messages;
    }
    // Drop oldest non-system messages until we fit
    let n = messages.len();
    let keep_start = config.keep_start.min(n);
    let keep_end_start = n.saturating_sub(config.keep_end);
    let mut drop_indices: Vec<usize> = (keep_start..keep_end_start).collect();
    drop_indices.reverse(); // drop from middle, oldest first
    let mut result = messages;
    for idx in drop_indices {
        if idx < result.len() {
            result.remove(idx);
            let new_total: usize = estimate_session_tokens(&result);
            if new_total <= max_tok {
                break;
            }
        }
    }
    result
}

fn build_session_summary(messages: &[SessionMessage]) -> String {
    if messages.is_empty() {
        return String::new();
    }
    let tool_events = messages
        .iter()
        .filter(|m| !m.tool_calls.is_empty() || m.tool_call_id.is_some())
        .count();
    let texts: Vec<String> = messages
        .iter()
        .map(|m| content_to_string(&m.content))
        .collect();
    let code_events = texts
        .iter()
        .filter(|t| t.contains("```") || t.contains("fn ") || t.contains("class "))
        .count();
    let mut highlights = Vec::new();
    for text in &texts {
        if let Some(sentence) = first_sentence(text) {
            if !highlights.iter().any(|h: &String| h == &sentence) {
                highlights.push(sentence);
            }
            if highlights.len() >= 6 {
                break;
            }
        }
    }
    let mut summary = format!(
        "[Context compaction: {} message(s) summarized]",
        messages.len()
    );
    if tool_events > 0 {
        summary.push_str(&format!(" {tool_events} tool event(s)."));
    }
    if code_events > 0 {
        summary.push_str(&format!(" {code_events} code event(s)."));
    }
    if !highlights.is_empty() {
        summary.push_str(" Key: ");
        summary.push_str(&highlights.join(" | "));
    }
    summary
}

// ── Legacy helpers (kept for existing tests) ────────────────────────

/// A message with importance score
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WeightedMessage {
    pub content: String,
    pub role: String,
    pub importance: f64,
    pub is_tool_call: bool,
    pub is_tool_result: bool,
}

/// Result of context compaction
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompactionResult {
    pub messages: Vec<WeightedMessage>,
    pub original_count: usize,
    pub compacted_count: usize,
    pub tokens_saved: Option<usize>,
    pub summary: Option<String>,
}

/// Context compactor for managing conversation history
pub struct ContextCompactor {
    config: CompactionConfig,
}

impl ContextCompactor {
    pub fn new(config: CompactionConfig) -> Self {
        Self { config }
    }

    pub fn with_defaults() -> Self {
        Self::new(CompactionConfig::default())
    }

    pub fn set_config(&mut self, config: CompactionConfig) {
        self.config = config;
    }

    pub fn config(&self) -> &CompactionConfig {
        &self.config
    }

    pub fn compact(&self, messages: &[String]) -> Result<CompactionResult, String> {
        match self.config.strategy {
            CompactionStrategy::SlidingWindow => self.compact_sliding_window(messages),
            CompactionStrategy::Summary => self.compact_with_summary(messages),
            CompactionStrategy::ImportanceBased => self.compact_by_importance(messages),
            CompactionStrategy::Adaptive => self.compact_adaptive(messages),
        }
    }

    fn compact_sliding_window(&self, messages: &[String]) -> Result<CompactionResult, String> {
        if messages.len() <= self.config.max_messages {
            return Ok(CompactionResult {
                messages: messages
                    .iter()
                    .enumerate()
                    .map(|(i, m)| WeightedMessage {
                        content: m.clone(),
                        role: if i % 2 == 0 {
                            "user".to_string()
                        } else {
                            "assistant".to_string()
                        },
                        importance: 1.0,
                        is_tool_call: false,
                        is_tool_result: false,
                    })
                    .collect(),
                original_count: messages.len(),
                compacted_count: messages.len(),
                tokens_saved: None,
                summary: None,
            });
        }

        let keep_start = self.config.keep_start.min(messages.len() / 2);
        let keep_end = self.config.keep_end.min(messages.len() / 2);

        let mut result = Vec::new();

        for msg in messages.iter().take(keep_start) {
            result.push(WeightedMessage {
                content: msg.clone(),
                role: "system".to_string(),
                importance: 1.0,
                is_tool_call: false,
                is_tool_result: false,
            });
        }

        for msg in messages.iter().skip(messages.len() - keep_end) {
            result.push(WeightedMessage {
                content: msg.clone(),
                role: "user".to_string(),
                importance: 1.0,
                is_tool_call: false,
                is_tool_result: false,
            });
        }

        let compacted_count = result.len();
        Ok(CompactionResult {
            messages: result,
            original_count: messages.len(),
            compacted_count,
            tokens_saved: None,
            summary: Some(format!(
                "Kept {} start and {} end messages",
                keep_start, keep_end
            )),
        })
    }

    fn compact_with_summary(&self, messages: &[String]) -> Result<CompactionResult, String> {
        if messages.len() <= self.config.max_messages {
            return self.compact_sliding_window(messages);
        }

        let keep_start = self.config.keep_start.min(messages.len() / 2);
        let keep_end = self.config.keep_end.min(messages.len() / 2);
        let summary_start = keep_start;
        let summary_end = messages.len().saturating_sub(keep_end);
        let summarized = &messages[summary_start..summary_end];

        let mut compacted = Vec::new();
        for (index, msg) in messages.iter().take(keep_start).enumerate() {
            compacted.push(WeightedMessage {
                content: msg.clone(),
                role: role_for_index(index),
                importance: 1.0,
                is_tool_call: msg.contains("tool_call"),
                is_tool_result: msg.contains("tool_result"),
            });
        }

        let summary = build_deterministic_summary(summarized);
        if !summary.is_empty() {
            compacted.push(WeightedMessage {
                content: summary.clone(),
                role: "system".to_string(),
                importance: 0.8,
                is_tool_call: false,
                is_tool_result: false,
            });
        }

        for (index, msg) in messages.iter().enumerate().skip(summary_end) {
            compacted.push(WeightedMessage {
                content: msg.clone(),
                role: role_for_index(index),
                importance: 1.0,
                is_tool_call: msg.contains("tool_call"),
                is_tool_result: msg.contains("tool_result"),
            });
        }

        let original_tokens = estimate_tokens(messages);
        let compacted_text: Vec<String> = compacted.iter().map(|msg| msg.content.clone()).collect();
        let compacted_tokens = estimate_tokens(&compacted_text);
        let compacted_count = compacted.len();

        Ok(CompactionResult {
            messages: compacted,
            original_count: messages.len(),
            compacted_count,
            tokens_saved: Some(original_tokens.saturating_sub(compacted_tokens)),
            summary: Some(format!(
                "Summarized {} middle message(s) between {} preserved start and {} preserved recent message(s).",
                summarized.len(),
                keep_start,
                keep_end
            )),
        })
    }

    fn compact_by_importance(&self, messages: &[String]) -> Result<CompactionResult, String> {
        let mut weighted: Vec<WeightedMessage> = messages
            .iter()
            .enumerate()
            .map(|(i, m)| {
                let importance = self.score_importance(m, i, messages.len());
                WeightedMessage {
                    content: m.clone(),
                    role: if i % 2 == 0 {
                        "user".to_string()
                    } else {
                        "assistant".to_string()
                    },
                    importance,
                    is_tool_call: m.contains("tool_call"),
                    is_tool_result: m.contains("tool_result"),
                }
            })
            .collect();

        weighted.sort_by(|a, b| b.importance.partial_cmp(&a.importance).unwrap());

        let keep_count = self.config.max_messages.min(weighted.len());
        weighted.truncate(keep_count);

        weighted.sort_by(|a, b| a.content.cmp(&b.content));

        Ok(CompactionResult {
            messages: weighted,
            original_count: messages.len(),
            compacted_count: keep_count,
            tokens_saved: None,
            summary: None,
        })
    }

    fn compact_adaptive(&self, messages: &[String]) -> Result<CompactionResult, String> {
        let total_tokens = estimate_tokens(messages);

        let strategy = if total_tokens < 4000 {
            CompactionStrategy::SlidingWindow
        } else if total_tokens < 16000 {
            CompactionStrategy::Summary
        } else {
            CompactionStrategy::ImportanceBased
        };

        let mut config = self.config.clone();
        config.strategy = strategy;

        let compactor = ContextCompactor::new(config);
        compactor.compact(messages)
    }

    fn score_importance(&self, content: &str, index: usize, total: usize) -> f64 {
        let mut score = 0.5;

        let recency = 1.0 - (index as f64 / total as f64);
        score += recency * 0.3;

        if content.contains("tool_call") || content.contains("tool_result") {
            score += 0.2;
        }

        if content.contains("```") || content.contains("fn ") || content.contains("const ") {
            score += 0.1;
        }

        if content.contains("system") || content.contains("instruction") {
            score += 0.15;
        }

        score.min(1.0)
    }
}

fn estimate_tokens(messages: &[String]) -> usize {
    messages.iter().map(|m| estimate_tokens_in_string(m)).sum()
}

fn estimate_tokens_in_string(s: &str) -> usize {
    s.len() / 4
}

fn role_for_index(index: usize) -> String {
    if index.is_multiple_of(2) {
        "user".to_string()
    } else {
        "assistant".to_string()
    }
}

fn build_deterministic_summary(messages: &[String]) -> String {
    if messages.is_empty() {
        return String::new();
    }

    let tool_events = messages
        .iter()
        .filter(|message| message.contains("tool_call") || message.contains("tool_result"))
        .count();
    let code_events = messages
        .iter()
        .filter(|message| {
            message.contains("```") || message.contains("fn ") || message.contains("class ")
        })
        .count();
    let mut highlights = Vec::new();
    for message in messages
        .iter()
        .filter_map(|message| first_sentence(message))
    {
        if !highlights.iter().any(|item| item == &message) {
            highlights.push(message);
        }
        if highlights.len() >= 6 {
            break;
        }
    }

    let mut summary = format!("Summary of {} compacted message(s):", messages.len());
    if tool_events > 0 {
        summary.push_str(&format!(" {tool_events} tool-related event(s)."));
    }
    if code_events > 0 {
        summary.push_str(&format!(" {code_events} code-related event(s)."));
    }
    if !highlights.is_empty() {
        summary.push_str(" Key points: ");
        summary.push_str(&highlights.join(" | "));
    }
    summary
}

fn first_sentence(message: &str) -> Option<String> {
    let trimmed = message.trim();
    if trimmed.is_empty() {
        return None;
    }
    let end = trimmed
        .char_indices()
        .find_map(|(index, ch)| matches!(ch, '.' | '!' | '?' | '\n').then_some(index))
        .unwrap_or(trimmed.len());
    let mut sentence = trimmed[..end].trim().to_string();
    const MAX_LEN: usize = 180;
    if sentence.len() > MAX_LEN {
        sentence.truncate(MAX_LEN);
        sentence.push_str("...");
    }
    (!sentence.is_empty()).then_some(sentence)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_sliding_window_compaction() {
        let compactor = ContextCompactor::new(CompactionConfig {
            strategy: CompactionStrategy::SlidingWindow,
            max_messages: 10,
            keep_start: 2,
            keep_end: 3,
            ..Default::default()
        });

        let messages: Vec<String> = (0..20).map(|i| format!("Message {}", i)).collect();
        let result = compactor.compact(&messages).unwrap();

        assert_eq!(result.original_count, 20);
        assert_eq!(result.compacted_count, 5); // 2 start + 3 end
    }

    #[test]
    fn test_importance_scoring() {
        let compactor = ContextCompactor::with_defaults();

        let tool_msg = "tool_call: read_file";
        let normal_msg = "What is the capital of France?";

        let tool_score = compactor.score_importance(tool_msg, 0, 10);
        let normal_score = compactor.score_importance(normal_msg, 0, 10);

        assert!(tool_score > normal_score);
    }

    #[test]
    fn test_adaptive_strategy_selection() {
        let config = CompactionConfig {
            strategy: CompactionStrategy::Adaptive,
            ..Default::default()
        };
        let compactor = ContextCompactor::new(config);

        let small_messages: Vec<String> = (0..10).map(|i| format!("Message {}", i)).collect();
        let result = compactor.compact(&small_messages).unwrap();
        assert!(result.compacted_count <= 10);
    }

    // ── New session-aware compaction tests ──

    fn make_msg(role: &str, text: &str) -> SessionMessage {
        SessionMessage::new(role, json!(text))
    }

    fn make_tool_result(tool_call_id: &str, text: &str) -> SessionMessage {
        SessionMessage::tool_result(tool_call_id, json!(text))
    }

    fn make_assistant_with_tools(tool_names: &[&str]) -> SessionMessage {
        let calls: Vec<serde_json::Value> = tool_names
            .iter()
            .enumerate()
            .map(|(i, name)| {
                json!({
                    "id": format!("call_{i}"),
                    "type": "function",
                    "function": {"name": name, "arguments": "{}"}
                })
            })
            .collect();
        SessionMessage::with_tool_calls("assistant", json!(""), calls)
    }

    #[test]
    fn short_history_not_compacted() {
        let msgs = vec![
            make_msg("system", "You are helpful."),
            make_msg("user", "Hello"),
            make_msg("assistant", "Hi!"),
        ];
        let config = CompactionConfig::default(); // max_messages = 100
        let result = compact_session_messages(&msgs, &config);
        assert_eq!(result.len(), 3);
    }

    #[test]
    fn long_history_compacted_sliding() {
        let mut msgs = vec![make_msg("system", "System prompt")];
        for i in 0..50 {
            msgs.push(make_msg("user", &format!("Question {i}")));
            msgs.push(make_msg("assistant", &format!("Answer {i}")));
        }
        let config = CompactionConfig {
            strategy: CompactionStrategy::SlidingWindow,
            max_messages: 20,
            keep_start: 2,
            keep_end: 10,
            ..Default::default()
        };
        let result = compact_session_messages(&msgs, &config);
        assert!(result.len() <= 20);
        // First message preserved
        assert_eq!(result[0].role, "system");
        // Last messages preserved
        let last = &result[result.len() - 1];
        assert_eq!(last.content, json!("Answer 49"));
    }

    #[test]
    fn system_and_recent_always_preserved() {
        let mut msgs = vec![
            make_msg("system", "System A"),
            make_msg("system", "System B"),
        ];
        for i in 0..30 {
            msgs.push(make_msg("user", &format!("U{i}")));
            msgs.push(make_msg("assistant", &format!("A{i}")));
        }
        let config = CompactionConfig {
            strategy: CompactionStrategy::SlidingWindow,
            max_messages: 10,
            keep_start: 2,
            keep_end: 5,
            ..Default::default()
        };
        let result = compact_session_messages(&msgs, &config);
        assert_eq!(result[0].content, json!("System A"));
        assert_eq!(result[1].content, json!("System B"));
        assert_eq!(result.last().unwrap().content, json!("A29"));
    }

    #[test]
    fn tool_call_and_result_not_split() {
        let mut msgs = vec![make_msg("system", "sys")];
        for i in 0..20 {
            msgs.push(make_msg("user", &format!("q{i}")));
            msgs.push(make_msg("assistant", &format!("a{i}")));
        }
        // Insert tool call pair near the cut boundary
        msgs.push(make_msg("user", "Do something"));
        msgs.push(make_assistant_with_tools(&["file_ops"]));
        msgs.push(make_tool_result("call_0", "done"));
        msgs.push(make_msg("assistant", "I did it."));
        // Add more recent messages
        for i in 0..5 {
            msgs.push(make_msg("user", &format!("follow{i}")));
            msgs.push(make_msg("assistant", &format!("resp{i}")));
        }

        let config = CompactionConfig {
            strategy: CompactionStrategy::SlidingWindow,
            max_messages: 15,
            keep_start: 1,
            keep_end: 12,
            ..Default::default()
        };
        let result = compact_session_messages(&msgs, &config);
        // Find any tool results — verify their preceding assistant has tool_calls
        for (i, msg) in result.iter().enumerate() {
            if msg.role == "tool" {
                assert!(i > 0, "tool result at index 0 is orphaned");
                // Walk backward to find the matching assistant
                let mut found_assistant = false;
                for j in (0..i).rev() {
                    if result[j].role == "assistant" && !result[j].tool_calls.is_empty() {
                        found_assistant = true;
                        break;
                    }
                    if result[j].role != "tool" {
                        break;
                    }
                }
                assert!(found_assistant, "tool result at index {i} is orphaned");
            }
        }
    }

    #[test]
    fn adaptive_strategy_uses_sliding_for_small() {
        let msgs: Vec<SessionMessage> = (0..5)
            .map(|i| make_msg("user", &format!("msg{i}")))
            .collect();
        let config = CompactionConfig {
            strategy: CompactionStrategy::Adaptive,
            max_messages: 3,
            keep_start: 1,
            keep_end: 1,
            ..Default::default()
        };
        let result = compact_session_messages(&msgs, &config);
        assert!(result.len() <= 5);
    }

    #[test]
    fn config_from_extras_defaults() {
        let extras = std::collections::BTreeMap::new();
        let config = compaction_config_from_extras(&extras).unwrap();
        assert_eq!(config.strategy, CompactionStrategy::SlidingWindow);
        assert_eq!(config.max_messages, 100);
    }

    #[test]
    fn config_from_extras_custom() {
        let mut extras = std::collections::BTreeMap::new();
        extras.insert("compaction_strategy".to_string(), json!("importance"));
        extras.insert("compaction_max_messages".to_string(), json!(50));
        extras.insert("compaction_keep_start".to_string(), json!(3));
        extras.insert("compaction_keep_end".to_string(), json!(8));
        let config = compaction_config_from_extras(&extras).unwrap();
        assert_eq!(config.strategy, CompactionStrategy::ImportanceBased);
        assert_eq!(config.max_messages, 50);
        assert_eq!(config.keep_start, 3);
        assert_eq!(config.keep_end, 8);
    }

    #[test]
    fn config_from_extras_disabled() {
        let mut extras = std::collections::BTreeMap::new();
        extras.insert("compaction_enabled".to_string(), json!(false));
        assert!(compaction_config_from_extras(&extras).is_none());
    }
}
