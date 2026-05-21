//! Core MCP types and data structures.
//!
//! These types follow the Model Context Protocol specification:
//! - https://modelcontextprotocol.io/specification

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

/// MCP protocol version
pub const MCP_VERSION: &str = "2024-11-05";

/// Request ID for correlating requests and responses
pub type RequestId = String;

// ============================================================================
// Core Protocol Types
// ============================================================================

/// A request sent to an MCP server
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Request {
    /// Unique identifier for this request
    pub id: RequestId,
    /// The method to invoke
    pub method: String,
    /// Optional parameters
    #[serde(skip_serializing_if = "Option::is_none")]
    pub params: Option<Value>,
}

/// A response from an MCP server
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Response {
    /// The request ID this response corresponds to
    pub id: RequestId,
    /// The result of the request
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    /// Error if the request failed
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<ErrorData>,
}

/// Error data for failed requests
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorData {
    /// Error code
    pub code: i32,
    /// Human-readable error message
    pub message: String,
    /// Optional additional data
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
}

/// Standard error codes
pub mod error_codes {
    pub const PARSE_ERROR: i32 = -32700;
    pub const INVALID_REQUEST: i32 = -32600;
    pub const METHOD_NOT_FOUND: i32 = -32601;
    pub const INVALID_PARAMS: i32 = -32602;
    pub const INTERNAL_ERROR: i32 = -32603;
}

// ============================================================================
// Initialization
// ============================================================================

/// Initialization request parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InitializeParams {
    /// Protocol version
    pub protocolVersion: String,
    /// Client capabilities
    pub capabilities: ClientCapabilities,
    /// Client information
    pub clientInfo: Implementation,
}

/// Implementation information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Implementation {
    /// Name of the implementation
    pub name: String,
    /// Version of the implementation
    pub version: String,
}

/// Client capabilities
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ClientCapabilities {
    /// Experimental client capabilities
    #[serde(skip_serializing_if = "Option::is_none")]
    pub experimental: Option<HashMap<String, Value>>,
    /// Sampling capabilities
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sampling: Option<SamplingCapabilities>,
}

/// Sampling capabilities
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SamplingCapabilities {}

/// Initialization result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InitializeResult {
    /// Protocol version
    pub protocolVersion: String,
    /// Server capabilities
    pub capabilities: ServerCapabilities,
    /// Server information
    pub serverInfo: Implementation,
    /// Instructions for the client
    #[serde(skip_serializing_if = "Option::is_none")]
    pub instructions: Option<String>,
}

/// Server capabilities
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ServerCapabilities {
    /// Experimental server capabilities
    #[serde(skip_serializing_if = "Option::is_none")]
    pub experimental: Option<HashMap<String, Value>>,
    /// Logging capabilities
    #[serde(skip_serializing_if = "Option::is_none")]
    pub logging: Option<LoggingCapabilities>,
    /// Prompt capabilities
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prompts: Option<PromptCapabilities>,
    /// Resource capabilities
    #[serde(skip_serializing_if = "Option::is_none")]
    pub resources: Option<ResourceCapabilities>,
    /// Tool capabilities
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tools: Option<ToolCapabilities>,
}

/// Logging capabilities
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct LoggingCapabilities {}

/// Prompt capabilities
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PromptCapabilities {
    /// Whether the server lists prompts
    #[serde(default)]
    pub listChanged: bool,
}

/// Resource capabilities
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ResourceCapabilities {
    /// Whether the server subscribes to resources
    #[serde(default)]
    pub subscribe: bool,
    /// Whether the server lists resources
    #[serde(default)]
    pub listChanged: bool,
}

/// Tool capabilities
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ToolCapabilities {
    /// Whether the server lists tools
    #[serde(default)]
    pub listChanged: bool,
}

// ============================================================================
// Tools
// ============================================================================

/// A tool that can be invoked
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Tool {
    /// Unique tool name
    pub name: String,
    /// Human-readable description
    pub description: Option<String>,
    /// Input schema (JSON Schema)
    pub inputSchema: ToolInputSchema,
    /// Optional output schema for structured output
    #[serde(skip_serializing_if = "Option::is_none")]
    pub outputSchema: Option<ToolOutputSchema>,
}

/// Tool input schema
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolInputSchema {
    /// JSON Schema type
    #[serde(default = "default_object_type")]
    pub r#type: String,
    /// Schema properties
    #[serde(default)]
    pub properties: HashMap<String, SchemaProperty>,
    /// Required properties
    #[serde(default)]
    pub required: Vec<String>,
    /// Additional schema fields
    #[serde(flatten)]
    pub additional: HashMap<String, Value>,
}

fn default_object_type() -> String {
    "object".to_string()
}

/// A property in the input schema
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SchemaProperty {
    /// Property type
    pub r#type: String,
    /// Human-readable description
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    /// Default value
    #[serde(skip_serializing_if = "Option::is_none")]
    pub default: Option<Value>,
    /// Enumerated values
    #[serde(skip_serializing_if = "Option::is_none")]
    pub enum_values: Option<Vec<Value>>,
    /// Additional schema fields
    #[serde(flatten)]
    pub additional: HashMap<String, Value>,
}

/// Tool output schema
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolOutputSchema {
    /// JSON Schema type
    #[serde(default = "default_object_type")]
    pub r#type: String,
    /// Schema properties
    #[serde(default)]
    pub properties: HashMap<String, SchemaProperty>,
}

/// Tool invocation request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CallToolParams {
    /// Tool name to invoke
    pub name: String,
    /// Tool arguments
    #[serde(default)]
    pub arguments: HashMap<String, Value>,
}

/// Tool invocation result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CallToolResult {
    /// Tool output content
    pub content: Vec<ToolContent>,
    /// Whether the tool encountered an error
    #[serde(default)]
    pub is_error: bool,
}

/// Tool content types
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum ToolContent {
    /// Plain text content
    Text { text: String },
    /// Image content (base64 encoded)
    Image { data: String, mimeType: String },
    /// Embedded resource
    Resource { resource: EmbeddedResource },
}

/// Embedded resource
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmbeddedResource {
    /// Resource URI
    pub uri: String,
    /// Resource name
    pub name: String,
    /// Optional MIME type
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mimeType: Option<String>,
    /// Text content
    #[serde(skip_serializing_if = "Option::is_none")]
    pub text: Option<String>,
    /// Binary content (base64)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub blob: Option<String>,
}

/// List of available tools
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListToolsResult {
    /// Available tools
    pub tools: Vec<Tool>,
}

// ============================================================================
// Resources
// ============================================================================

/// A resource that can be read
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Resource {
    /// Resource URI
    pub uri: String,
    /// Resource name
    pub name: String,
    /// Optional MIME type
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mimeType: Option<String>,
    /// Human-readable description
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
}

/// List of available resources
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListResourcesResult {
    /// Available resources
    pub resources: Vec<Resource>,
}

/// Resource template for parameterized URIs
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceTemplate {
    /// URI template (RFC 6570)
    pub uriTemplate: String,
    /// Template name
    pub name: String,
    /// Optional MIME type
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mimeType: Option<String>,
    /// Human-readable description
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
}

/// List of resource templates
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListResourceTemplatesResult {
    /// Available templates
    pub resourceTemplates: Vec<ResourceTemplate>,
}

/// Read resource parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReadResourceParams {
    /// Resource URI to read
    pub uri: String,
}

/// Read resource result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReadResourceResult {
    /// Resource contents
    pub contents: Vec<ResourceContents>,
}

/// Resource contents
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "mimeType")]
pub enum ResourceContents {
    /// Text resource
    #[serde(rename = "text/plain")]
    Text {
        uri: String,
        text: String,
    },
    /// Binary resource
    #[serde(rename = "application/octet-stream")]
    Binary {
        uri: String,
        blob: String,
    },
}

// ============================================================================
// Prompts
// ============================================================================

/// A prompt template
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Prompt {
    /// Unique prompt name
    pub name: String,
    /// Human-readable description
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    /// Optional arguments
    #[serde(skip_serializing_if = "Option::is_none")]
    pub arguments: Option<Vec<PromptArgument>>,
}

/// Prompt argument
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptArgument {
    /// Argument name
    pub name: String,
    /// Human-readable description
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    /// Whether argument is required
    #[serde(default)]
    pub required: bool,
}

/// List of available prompts
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListPromptsResult {
    /// Available prompts
    pub prompts: Vec<Prompt>,
}

/// Get prompt parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetPromptParams {
    /// Prompt name
    pub name: String,
    /// Optional arguments
    #[serde(default)]
    pub arguments: HashMap<String, String>,
}

/// Prompt message
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptMessage {
    /// Message role
    pub role: String,
    /// Message content
    pub content: PromptContent,
}

/// Prompt content
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum PromptContent {
    /// Plain text
    Text { text: String },
    /// Image
    Image { data: String, mimeType: String },
}

/// Get prompt result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetPromptResult {
    /// Prompt description
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    /// Prompt messages
    pub messages: Vec<PromptMessage>,
}

// ============================================================================
// Logging
// ============================================================================

/// Log level
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum LogLevel {
    Debug,
    Info,
    Notice,
    Warning,
    Error,
    Critical,
    Alert,
    Emergency,
}

/// Logging message
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoggingMessageParams {
    /// Log level
    pub level: LogLevel,
    /// Logger name
    #[serde(skip_serializing_if = "Option::is_none")]
    pub logger: Option<String>,
    /// Log data
    pub data: Value,
}

// ============================================================================
// Notifications
// ============================================================================

/// A notification (no response expected)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Notification {
    /// Notification method
    pub method: String,
    /// Optional parameters
    #[serde(skip_serializing_if = "Option::is_none")]
    pub params: Option<Value>,
}

/// Notification methods
pub mod notification_methods {
    pub const CANCELLED: &str = "notifications/cancelled";
    pub const PROGRESS: &str = "notifications/progress";
    pub const TOOLS_LIST_CHANGED: &str = "notifications/tools/list_changed";
    pub const RESOURCES_LIST_CHANGED: &str = "notifications/resources/list_changed";
    pub const PROMPTS_LIST_CHANGED: &str = "notifications/prompts/list_changed";
    pub const LOGGING: &str = "notifications/message";
}

// ============================================================================
// Progress
// ============================================================================

/// Progress notification parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProgressParams {
    /// Progress token
    pub progressToken: String,
    /// Current progress
    pub progress: f64,
    /// Total work (optional)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub total: Option<f64>,
}

// ============================================================================
// Sampling (client-side)
// ============================================================================

/// Sampling request (client asks server for model completion)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SamplingParams {
    /// Messages for the model
    pub messages: Vec<SamplingMessage>,
    /// Optional system prompt
    #[serde(skip_serializing_if = "Option::is_none")]
    pub system: Option<String>,
    /// Optional temperature
    #[serde(skip_serializing_if = "Option::is_none")]
    pub temperature: Option<f64>,
    /// Optional max tokens
    #[serde(skip_serializing_if = "Option::is_none")]
    pub maxTokens: Option<u32>,
    /// Optional stop sequences
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stopSequences: Option<Vec<String>>,
    /// Optional top P
    #[serde(skip_serializing_if = "Option::is_none")]
    pub topP: Option<f64>,
    /// Optional top K
    #[serde(skip_serializing_if = "Option::is_none")]
    pub topK: Option<u32>,
}

/// Sampling message
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SamplingMessage {
    /// Message role
    pub role: String,
    /// Message content
    pub content: SamplingContent,
}

/// Sampling content
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum SamplingContent {
    /// Text content
    Text { text: String },
    /// Image content
    Image { data: String, mimeType: String },
}

/// Sampling result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SamplingResult {
    /// Model response
    pub model: String,
    /// Stop reason
    pub stopReason: String,
    /// Usage statistics
    pub usage: Usage,
    /// Assistant message
    pub message: SamplingMessage,
}

/// Usage statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Usage {
    /// Input tokens
    pub inputTokens: u32,
    /// Output tokens
    pub outputTokens: u32,
}

// ============================================================================
// Configuration
// ============================================================================

/// MCP server configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpServerConfig {
    /// Server name
    pub name: String,
    /// Command to execute
    pub command: String,
    /// Command arguments
    #[serde(default)]
    pub args: Vec<String>,
    /// Environment variables
    #[serde(default)]
    pub env: HashMap<String, String>,
    /// Whether the server is enabled
    #[serde(default = "default_true")]
    pub enabled: bool,
    /// Timeout in seconds
    #[serde(default = "default_timeout")]
    pub timeout_seconds: u64,
    /// Tools to expose (empty = all)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub enabled_tools: Option<Vec<String>>,
    /// Server transport type
    #[serde(default)]
    pub transport: McpTransport,
}

fn default_true() -> bool {
    true
}

fn default_timeout() -> u64 {
    30
}

/// Transport type
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum McpTransport {
    #[default]
    Stdio,
    Sse,
    Websocket,
}

/// MCP server status
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpServerStatus {
    /// Server name
    pub name: String,
    /// Whether the server is running
    pub running: bool,
    /// Whether the server is initialized
    pub initialized: bool,
    /// Available tools count
    pub tool_count: usize,
    /// Available resources count
    pub resource_count: usize,
    /// Available prompts count
    pub prompt_count: usize,
    /// Last error (if any)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_error: Option<String>,
}
