//! Context compaction strategies for managing large conversation histories.
//!
//! This module provides various strategies for reducing context size while
//! preserving important information for LLM conversations.

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

/// Compaction strategy to use
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum CompactionStrategy {
    /// Keep only the most recent messages
    SlidingWindow,
    /// Summarize older messages
    Summary,
    /// Keep messages based on importance scoring
    ImportanceBased,
    /// Adaptive strategy that chooses based on context size
    Adaptive,
}

impl Default for CompactionStrategy {
    fn default() -> Self {
        Self::SlidingWindow
    }
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

/// A message with importance score
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WeightedMessage {
    /// Original message content
    pub content: String,
    /// Role (user, assistant, system, tool)
    pub role: String,
    /// Importance score (0.0 to 1.0)
    pub importance: f64,
    /// Whether this message is a tool call
    pub is_tool_call: bool,
    /// Whether this message is a tool result
    pub is_tool_result: bool,
}

/// Result of context compaction
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompactionResult {
    /// Compacted messages
    pub messages: Vec<WeightedMessage>,
    /// Original message count
    pub original_count: usize,
    /// Compacted message count
    pub compacted_count: usize,
    /// Tokens saved (estimated)
    pub tokens_saved: Option<usize>,
    /// Summary of removed messages (if applicable)
    pub summary: Option<String>,
}

/// Context compactor for managing conversation history
pub struct ContextCompactor {
    config: CompactionConfig,
}

impl ContextCompactor {
    /// Create a new context compactor with the given configuration
    pub fn new(config: CompactionConfig) -> Self {
        Self { config }
    }

    /// Create a new context compactor with default configuration
    pub fn with_defaults() -> Self {
        Self::new(CompactionConfig::default())
    }

    /// Update the configuration
    pub fn set_config(&mut self, config: CompactionConfig) {
        self.config = config;
    }

    /// Get the current configuration
    pub fn config(&self) -> &CompactionConfig {
        &self.config
    }

    /// Compact a list of messages according to the configured strategy
    pub fn compact(&self, messages: &[String]) -> Result<CompactionResult, String> {
        match self.config.strategy {
            CompactionStrategy::SlidingWindow => self.compact_sliding_window(messages),
            CompactionStrategy::Summary => self.compact_with_summary(messages),
            CompactionStrategy::ImportanceBased => self.compact_by_importance(messages),
            CompactionStrategy::Adaptive => self.compact_adaptive(messages),
        }
    }

    /// Sliding window compaction: keep first N and last M messages
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

        // Keep start messages
        for msg in messages.iter().take(keep_start) {
            result.push(WeightedMessage {
                content: msg.clone(),
                role: "system".to_string(),
                importance: 1.0,
                is_tool_call: false,
                is_tool_result: false,
            });
        }

        // Keep end messages
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

    /// Summary-based compaction: summarize older messages
    fn compact_with_summary(&self, messages: &[String]) -> Result<CompactionResult, String> {
        // For now, just use sliding window as a placeholder
        // In a real implementation, this would call an LLM to summarize
        self.compact_sliding_window(messages)
    }

    /// Importance-based compaction: score and keep most important messages
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

        // Sort by importance (descending)
        weighted.sort_by(|a, b| b.importance.partial_cmp(&a.importance).unwrap());

        // Keep top messages
        let keep_count = self.config.max_messages.min(weighted.len());
        weighted.truncate(keep_count);

        // Re-sort by original order
        weighted.sort_by(|a, b| a.content.cmp(&b.content));

        Ok(CompactionResult {
            messages: weighted,
            original_count: messages.len(),
            compacted_count: keep_count,
            tokens_saved: None,
            summary: None,
        })
    }

    /// Adaptive compaction: choose strategy based on context size
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

    /// Score the importance of a message
    fn score_importance(&self, content: &str, index: usize, total: usize) -> f64 {
        let mut score = 0.5;

        // Recent messages are more important
        let recency = 1.0 - (index as f64 / total as f64);
        score += recency * 0.3;

        // Tool calls and results are important
        if content.contains("tool_call") || content.contains("tool_result") {
            score += 0.2;
        }

        // Messages with code are important
        if content.contains("```") || content.contains("fn ") || content.contains("const ") {
            score += 0.1;
        }

        // System messages are important
        if content.contains("system") || content.contains("instruction") {
            score += 0.15;
        }

        score.min(1.0)
    }
}

/// Estimate the number of tokens in a list of messages
fn estimate_tokens(messages: &[String]) -> usize {
    messages.iter().map(|m| estimate_tokens_in_string(m)).sum()
}

/// Estimate tokens in a string (rough approximation)
fn estimate_tokens_in_string(s: &str) -> usize {
    // Rough estimate: 1 token ≈ 4 characters
    s.len() / 4
}

#[cfg(test)]
mod tests {
    use super::*;

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

        // Tool call should be more important
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

        // Small context should use sliding window
        let small_messages: Vec<String> = (0..10).map(|i| format!("Message {}", i)).collect();
        let result = compactor.compact(&small_messages).unwrap();
        assert!(result.compacted_count <= 10);
    }
}
