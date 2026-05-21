//! MCP Client implementation.
//!
//! The client connects to MCP servers, manages their lifecycle, and invokes tools.

use crate::transport::{StdioTransport, Transport};
use crate::types::*;
use anyhow::{anyhow, Result};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use tokio::sync::RwLock;
use tracing::info;

/// Request ID generator
struct RequestIdGenerator {
    counter: AtomicU64,
}

impl RequestIdGenerator {
    fn new() -> Self {
        Self {
            counter: AtomicU64::new(0),
        }
    }

    fn next(&self) -> RequestId {
        self.counter.fetch_add(1, Ordering::SeqCst).to_string()
    }
}

/// MCP Client for connecting to and interacting with MCP servers
pub struct McpClient {
    /// Server configuration
    config: McpServerConfig,
    /// Transport layer
    transport: Option<Box<dyn Transport + Send + Sync>>,
    /// Request ID generator
    request_id: RequestIdGenerator,
    /// Initialized state
    initialized: RwLock<bool>,
    /// Server capabilities
    capabilities: RwLock<Option<ServerCapabilities>>,
    /// Server info
    server_info: RwLock<Option<Implementation>>,
    /// Cached tools
    tools: RwLock<Vec<Tool>>,
    /// Cached resources
    resources: RwLock<Vec<Resource>>,
    /// Cached prompts
    prompts: RwLock<Vec<Prompt>>,
    /// Timeout for requests
    timeout_seconds: u64,
}

impl McpClient {
    /// Create a new MCP client from configuration
    pub fn new(config: McpServerConfig) -> Self {
        let timeout_seconds = config.timeout_seconds;
        Self {
            config,
            transport: None,
            request_id: RequestIdGenerator::new(),
            initialized: RwLock::new(false),
            capabilities: RwLock::new(None),
            server_info: RwLock::new(None),
            tools: RwLock::new(Vec::new()),
            resources: RwLock::new(Vec::new()),
            prompts: RwLock::new(Vec::new()),
            timeout_seconds,
        }
    }

    /// Create a client with stdio transport
    pub fn with_stdio(
        command: impl Into<String>,
        args: Vec<String>,
        env: HashMap<String, String>,
    ) -> Self {
        let command = command.into();
        let config = McpServerConfig {
            name: command.clone(),
            command,
            args,
            env,
            enabled: true,
            timeout_seconds: 30,
            enabled_tools: None,
            transport: McpTransport::Stdio,
        };
        Self::new(config)
    }

    /// Check if the client is connected
    pub fn is_connected(&self) -> bool {
        self.transport.is_some()
    }

    /// Check if the client is initialized
    pub async fn is_initialized(&self) -> bool {
        *self.initialized.read().await
    }

    /// Connect to the MCP server
    pub async fn connect(&mut self) -> Result<()> {
        if self.transport.is_some() {
            return Err(anyhow!("Already connected"));
        }

        info!("Connecting to MCP server: {}", self.config.name);

        let transport = match self.config.transport {
            McpTransport::Stdio => {
                StdioTransport::spawn(&self.config.command, &self.config.args, &self.config.env)?
            }
            McpTransport::Sse | McpTransport::Websocket => {
                return Err(anyhow!("Only stdio MCP transport is currently supported"));
            }
        };

        self.transport = Some(Box::new(transport));
        Ok(())
    }

    /// Initialize the MCP session
    pub async fn initialize(&mut self) -> Result<InitializeResult> {
        if !self.is_connected() {
            self.connect().await?;
        }

        if *self.initialized.read().await {
            return Err(anyhow!("Already initialized"));
        }

        info!("Initializing MCP session with {}", self.config.name);

        let params = InitializeParams {
            protocol_version: MCP_VERSION.to_string(),
            capabilities: ClientCapabilities::default(),
            client_info: Implementation {
                name: "reverie-cli".to_string(),
                version: env!("CARGO_PKG_VERSION").to_string(),
            },
        };
        let response = self
            .send("initialize", Some(serde_json::to_value(params)?))
            .await?;
        let result: InitializeResult = serde_json::from_value(response)?;
        *self.capabilities.write().await = Some(result.capabilities.clone());
        *self.server_info.write().await = Some(result.server_info.clone());
        *self.initialized.write().await = true;

        let _ = self.refresh_catalogs().await;
        Ok(result)
    }

    /// List available tools
    pub async fn list_tools(&mut self) -> Result<Vec<Tool>> {
        if !*self.initialized.read().await {
            return Err(anyhow!("Not initialized"));
        }

        let result: ListToolsResult = serde_json::from_value(self.send("tools/list", None).await?)?;
        *self.tools.write().await = result.tools.clone();
        Ok(self.tools.read().await.clone())
    }

    /// Call a tool
    pub async fn call_tool(
        &mut self,
        name: &str,
        arguments: HashMap<String, Value>,
    ) -> Result<CallToolResult> {
        if !*self.initialized.read().await {
            return Err(anyhow!("Not initialized"));
        }

        let params = CallToolParams {
            name: name.to_string(),
            arguments,
        };
        serde_json::from_value(
            self.send("tools/call", Some(serde_json::to_value(params)?))
                .await?,
        )
        .map_err(Into::into)
    }

    /// List available resources
    pub async fn list_resources(&mut self) -> Result<Vec<Resource>> {
        if !*self.initialized.read().await {
            return Err(anyhow!("Not initialized"));
        }

        let result: ListResourcesResult =
            serde_json::from_value(self.send("resources/list", None).await?)?;
        *self.resources.write().await = result.resources.clone();
        Ok(self.resources.read().await.clone())
    }

    /// Read a resource
    pub async fn read_resource(&mut self, uri: &str) -> Result<ResourceContents> {
        if !*self.initialized.read().await {
            return Err(anyhow!("Not initialized"));
        }

        let params = ReadResourceParams {
            uri: uri.to_string(),
        };
        let result: ReadResourceResult = serde_json::from_value(
            self.send("resources/read", Some(serde_json::to_value(params)?))
                .await?,
        )?;
        result
            .contents
            .into_iter()
            .next()
            .ok_or_else(|| anyhow!("Resource returned no contents: {uri}"))
    }

    /// List available prompts
    pub async fn list_prompts(&mut self) -> Result<Vec<Prompt>> {
        if !*self.initialized.read().await {
            return Err(anyhow!("Not initialized"));
        }

        let result: ListPromptsResult =
            serde_json::from_value(self.send("prompts/list", None).await?)?;
        *self.prompts.write().await = result.prompts.clone();
        Ok(self.prompts.read().await.clone())
    }

    /// Get a prompt
    pub async fn get_prompt(
        &mut self,
        name: &str,
        arguments: HashMap<String, String>,
    ) -> Result<GetPromptResult> {
        if !*self.initialized.read().await {
            return Err(anyhow!("Not initialized"));
        }

        let params = GetPromptParams {
            name: name.to_string(),
            arguments,
        };
        serde_json::from_value(
            self.send("prompts/get", Some(serde_json::to_value(params)?))
                .await?,
        )
        .map_err(Into::into)
    }

    /// Disconnect from the server
    pub async fn disconnect(&mut self) -> Result<()> {
        if let Some(mut transport) = self.transport.take() {
            transport.close().await?;
        }

        *self.initialized.write().await = false;
        self.tools.write().await.clear();
        self.resources.write().await.clear();
        self.prompts.write().await.clear();

        info!("Disconnected from MCP server: {}", self.config.name);

        Ok(())
    }

    /// Get server status
    pub fn status(&self) -> McpServerStatus {
        let tools = self.tools.blocking_read();
        let resources = self.resources.blocking_read();
        let prompts = self.prompts.blocking_read();

        McpServerStatus {
            name: self.config.name.clone(),
            running: self.transport.is_some(),
            initialized: *self.initialized.blocking_read(),
            tool_count: tools.len(),
            resource_count: resources.len(),
            prompt_count: prompts.len(),
            last_error: None,
        }
    }

    async fn refresh_catalogs(&mut self) -> Result<()> {
        let _ = self.list_tools().await;
        let _ = self.list_resources().await;
        let _ = self.list_prompts().await;
        Ok(())
    }

    async fn send(&mut self, method: &str, params: Option<Value>) -> Result<Value> {
        let transport = self
            .transport
            .as_mut()
            .ok_or_else(|| anyhow!("MCP transport is not connected"))?;
        let request = Request {
            id: self.request_id.next(),
            method: method.to_string(),
            params,
        };
        let response = tokio::time::timeout(
            Duration::from_secs(self.timeout_seconds.max(1)),
            transport.send_request(request),
        )
        .await
        .map_err(|_| anyhow!("MCP request timed out: {method}"))??;

        if let Some(error) = response.error {
            return Err(anyhow!("MCP error {}: {}", error.code, error.message));
        }
        Ok(response.result.unwrap_or_else(|| json!({})))
    }
}
