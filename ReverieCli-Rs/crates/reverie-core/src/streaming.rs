//! Streaming response handling for LLM conversations.
//!
//! This module provides utilities for handling streaming responses from
//! various LLM providers, including SSE (Server-Sent Events) handling.

use anyhow::{anyhow, Result};
use futures::StreamExt;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tokio::sync::mpsc;
use tracing::{debug, error};

/// Streaming event types
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum StreamingEvent {
    /// Start of streaming response
    Start { model: String },
    /// A chunk of the response
    Content {
        content: String,
        finish_reason: Option<String>,
    },
    /// Tool call request
    ToolCall {
        tool_call_id: String,
        name: String,
        arguments: String,
    },
    /// End of streaming response
    End {
        finish_reason: String,
        usage: Option<UsageInfo>,
    },
    /// Error during streaming
    Error { message: String },
    /// A retryable request error occurred and Reverie is waiting before retrying.
    RetryScheduled {
        message: String,
        attempt: u8,
        max_attempts: u8,
        retry_after_seconds: u64,
    },
}

/// Usage information from the model
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UsageInfo {
    pub prompt_tokens: u32,
    pub completion_tokens: u32,
    pub total_tokens: u32,
}

/// Configuration for streaming
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamingConfig {
    /// Whether to enable streaming
    pub enabled: bool,
    /// Timeout for the streaming connection
    pub timeout_seconds: u64,
    /// Buffer size for the event channel
    pub buffer_size: usize,
    /// Whether to include usage information
    pub include_usage: bool,
}

impl Default for StreamingConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            timeout_seconds: 300,
            buffer_size: 100,
            include_usage: true,
        }
    }
}

/// Result of a streaming operation
pub struct StreamingResult {
    /// Channel for receiving events
    pub rx: mpsc::Receiver<StreamingEvent>,
    /// Whether streaming was successful
    pub success: bool,
    /// Error message if failed
    pub error: Option<String>,
}

const REQUEST_RETRY_DELAYS_SECONDS: [u64; 5] = [1, 3, 5, 7, 15];
const REQUEST_RETRY_ATTEMPTS: u8 = REQUEST_RETRY_DELAYS_SECONDS.len() as u8;

fn retryable_status(status: reqwest::StatusCode) -> bool {
    matches!(status.as_u16(), 429 | 500 | 502 | 503 | 504)
}

/// Handle streaming response from an LLM
pub async fn handle_streaming(
    url: &str,
    headers: std::collections::HashMap<String, String>,
    body: serde_json::Value,
    config: StreamingConfig,
) -> Result<StreamingResult> {
    if !config.enabled {
        return Err(anyhow!("Streaming is disabled"));
    }

    let (tx, rx) = mpsc::channel(config.buffer_size);
    let url = url.to_string();

    let client = Client::builder()
        .timeout(Duration::from_secs(config.timeout_seconds))
        .build()?;

    tokio::spawn(async move {
        let mut last_error = None;
        for attempt in 0..=REQUEST_RETRY_ATTEMPTS {
            let mut request = client.post(&url);

            for (key, value) in &headers {
                request = request.header(key, value);
            }

            request = request.json(&body);

            match request.send().await {
                Ok(response) => {
                    let status = response.status();
                    if !status.is_success() {
                        let message = format!("streaming request failed with HTTP {status}");
                        if retryable_status(status) && attempt < REQUEST_RETRY_ATTEMPTS {
                            let delay = REQUEST_RETRY_DELAYS_SECONDS[attempt as usize];
                            let _ = tx
                                .send(StreamingEvent::RetryScheduled {
                                    message: message.clone(),
                                    attempt: attempt + 1,
                                    max_attempts: REQUEST_RETRY_ATTEMPTS,
                                    retry_after_seconds: delay,
                                })
                                .await;
                            tokio::time::sleep(Duration::from_secs(delay)).await;
                            last_error = Some(message);
                            continue;
                        }
                        let _ = tx.send(StreamingEvent::Error { message }).await;
                        return;
                    }

                    debug!("Received streaming response");
                    if let Err(e) = process_sse_stream(response, tx.clone()).await {
                        let message = e.to_string();
                        if attempt < REQUEST_RETRY_ATTEMPTS {
                            let delay = REQUEST_RETRY_DELAYS_SECONDS[attempt as usize];
                            let _ = tx
                                .send(StreamingEvent::RetryScheduled {
                                    message: message.clone(),
                                    attempt: attempt + 1,
                                    max_attempts: REQUEST_RETRY_ATTEMPTS,
                                    retry_after_seconds: delay,
                                })
                                .await;
                            tokio::time::sleep(Duration::from_secs(delay)).await;
                            last_error = Some(message);
                            continue;
                        }
                        error!("Error processing SSE stream: {}", e);
                        let _ = tx.send(StreamingEvent::Error { message }).await;
                    }
                    return;
                }
                Err(e) => {
                    let message = e.to_string();
                    if attempt < REQUEST_RETRY_ATTEMPTS {
                        let delay = REQUEST_RETRY_DELAYS_SECONDS[attempt as usize];
                        let _ = tx
                            .send(StreamingEvent::RetryScheduled {
                                message: message.clone(),
                                attempt: attempt + 1,
                                max_attempts: REQUEST_RETRY_ATTEMPTS,
                                retry_after_seconds: delay,
                            })
                            .await;
                        tokio::time::sleep(Duration::from_secs(delay)).await;
                        last_error = Some(message);
                        continue;
                    }
                    error!("Failed to send streaming request: {}", e);
                    let _ = tx.send(StreamingEvent::Error { message }).await;
                    return;
                }
            }
        }
        let _ = tx
            .send(StreamingEvent::Error {
                message: last_error.unwrap_or_else(|| "streaming retry exhausted".to_string()),
            })
            .await;
    });

    Ok(StreamingResult {
        rx,
        success: true,
        error: None,
    })
}

/// Process Server-Sent Events stream
async fn process_sse_stream(
    response: reqwest::Response,
    tx: mpsc::Sender<StreamingEvent>,
) -> Result<()> {
    let mut stream = response.bytes_stream();

    let mut current_content = String::new();
    let mut tool_calls: Vec<(String, String, String)> = Vec::new();

    while let Some(chunk_result) = stream.next().await {
        let chunk = chunk_result?;
        let chunk_str = String::from_utf8_lossy(&chunk);

        // Parse SSE events
        for line in chunk_str.lines() {
            if let Some(data) = line.strip_prefix("data: ") {
                if data == "[DONE]" {
                    // End of stream
                    let _ = tx
                        .send(StreamingEvent::End {
                            finish_reason: "stop".to_string(),
                            usage: None,
                        })
                        .await;
                    return Ok(());
                }

                // Try to parse as JSON
                if let Ok(event_data) = serde_json::from_str::<serde_json::Value>(data) {
                    // Extract content
                    if let Some(content) = event_data
                        .get("choices")
                        .and_then(|c| c.as_array())
                        .and_then(|c| c.first())
                        .and_then(|c| c.get("delta"))
                        .and_then(|d| d.get("content"))
                        .and_then(|c| c.as_str())
                    {
                        current_content.push_str(content);

                        let _ = tx
                            .send(StreamingEvent::Content {
                                content: content.to_string(),
                                finish_reason: None,
                            })
                            .await;
                    }

                    // Extract tool calls
                    if let Some(tool_calls_data) = event_data
                        .get("choices")
                        .and_then(|c| c.as_array())
                        .and_then(|c| c.first())
                        .and_then(|c| c.get("delta"))
                        .and_then(|d| d.get("tool_calls"))
                        .and_then(|t| t.as_array())
                    {
                        for tool_call in tool_calls_data {
                            if let Some(id) = tool_call.get("id").and_then(|i| i.as_str()) {
                                if let Some(name) = tool_call
                                    .get("function")
                                    .and_then(|f| f.get("name"))
                                    .and_then(|n| n.as_str())
                                {
                                    if let Some(arguments) = tool_call
                                        .get("function")
                                        .and_then(|f| f.get("arguments"))
                                        .and_then(|a| a.as_str())
                                    {
                                        tool_calls.push((
                                            id.to_string(),
                                            name.to_string(),
                                            arguments.to_string(),
                                        ));

                                        let _ = tx
                                            .send(StreamingEvent::ToolCall {
                                                tool_call_id: id.to_string(),
                                                name: name.to_string(),
                                                arguments: arguments.to_string(),
                                            })
                                            .await;
                                    }
                                }
                            }
                        }
                    }

                    // Extract finish reason
                    if let Some(finish_reason) = event_data
                        .get("choices")
                        .and_then(|c| c.as_array())
                        .and_then(|c| c.first())
                        .and_then(|c| c.get("finish_reason"))
                        .and_then(|f| f.as_str())
                    {
                        if finish_reason != "null" {
                            let _ = tx
                                .send(StreamingEvent::End {
                                    finish_reason: finish_reason.to_string(),
                                    usage: None,
                                })
                                .await;
                        }
                    }

                    // Extract usage
                    if let Some(usage) = event_data.get("usage") {
                        if let Ok(usage_info) = serde_json::from_value::<UsageInfo>(usage.clone()) {
                            // Update the last End event with usage
                            // For now, just log it
                            debug!("Usage: {:?}", usage_info);
                        }
                    }
                }
            }
        }
    }

    Ok(())
}

/// Aggregate streaming content into a complete response
pub fn aggregate_streaming_content(rx: &mut mpsc::Receiver<StreamingEvent>) -> Result<String> {
    let mut content = String::new();
    let mut tool_calls: Vec<(String, String, String)> = Vec::new();

    while let Some(event) = rx.blocking_recv() {
        match event {
            StreamingEvent::Content { content: c, .. } => {
                content.push_str(&c);
            }
            StreamingEvent::ToolCall {
                tool_call_id,
                name,
                arguments,
            } => {
                tool_calls.push((tool_call_id, name, arguments));
            }
            StreamingEvent::End { .. } => {
                break;
            }
            StreamingEvent::Error { message } => {
                return Err(anyhow!("Streaming error: {}", message));
            }
            StreamingEvent::RetryScheduled { .. } => {}
            _ => {}
        }
    }

    Ok(content)
}

/// Convert streaming events to a list of messages
pub fn streaming_events_to_messages(events: &[StreamingEvent]) -> Vec<serde_json::Value> {
    let mut messages = Vec::new();
    let mut current_content = String::new();
    let mut current_tool_calls: Vec<serde_json::Value> = Vec::new();

    for event in events {
        match event {
            StreamingEvent::Content { content, .. } => {
                current_content.push_str(content);
            }
            StreamingEvent::ToolCall {
                tool_call_id,
                name,
                arguments,
            } => {
                current_tool_calls.push(serde_json::json!({
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": arguments
                    }
                }));
            }
            StreamingEvent::End { .. } => {
                if !current_content.is_empty() {
                    messages.push(serde_json::json!({
                        "role": "assistant",
                        "content": current_content,
                        "tool_calls": current_tool_calls
                    }));
                }
                break;
            }
            _ => {}
        }
    }

    messages
}
