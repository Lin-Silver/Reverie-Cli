//! MCP Server implementation.
//!
//! Allows Reverie to function as an MCP server, exposing its capabilities to orchestrating agents.

use crate::types::*;
use anyhow::{anyhow, Context, Result};
use serde_json::{json, Value};
use std::collections::HashMap;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt};
use tokio::sync::RwLock;
use tracing::{debug, error, info, trace};

/// Tool handler function type
pub type ToolHandler = Box<dyn Fn(HashMap<String, Value>) -> Result<Value> + Send + Sync>;

/// Resource handler function type
pub type ResourceHandler = Box<dyn Fn(&str) -> Result<ResourceContents> + Send + Sync>;

/// Prompt handler function type
pub type PromptHandler =
    Box<dyn Fn(&str, HashMap<String, String>) -> Result<GetPromptResult> + Send + Sync>;

/// MCP Server that exposes Reverie capabilities
pub struct McpServer {
    /// Server name
    name: String,
    /// Server version
    version: String,
    /// Registered tools
    tools: RwLock<HashMap<String, ToolHandler>>,
    /// Registered resources
    resources: RwLock<HashMap<String, ResourceHandler>>,
    /// Registered prompts
    prompts: RwLock<HashMap<String, PromptHandler>>,
    /// Server capabilities
    capabilities: ServerCapabilities,
    /// Initialized state
    initialized: RwLock<bool>,
}

impl McpServer {
    /// Create a new MCP server
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            tools: RwLock::new(HashMap::new()),
            resources: RwLock::new(HashMap::new()),
            prompts: RwLock::new(HashMap::new()),
            capabilities: ServerCapabilities::default(),
            initialized: RwLock::new(false),
        }
    }

    /// Set server version
    pub fn with_version(mut self, version: impl Into<String>) -> Self {
        self.version = version.into();
        self
    }

    /// Enable tool capabilities
    pub fn with_tools(mut self) -> Self {
        self.capabilities.tools = Some(ToolCapabilities { listChanged: false });
        self
    }

    /// Enable resource capabilities
    pub fn with_resources(mut self) -> Self {
        self.capabilities.resources = Some(ResourceCapabilities {
            subscribe: false,
            listChanged: false,
        });
        self
    }

    /// Enable prompt capabilities
    pub fn with_prompts(mut self) -> Self {
        self.capabilities.prompts = Some(PromptCapabilities { listChanged: false });
        self
    }

    /// Register a tool
    pub async fn register_tool(
        &mut self,
        name: impl Into<String>,
        description: impl Into<String>,
        input_schema: ToolInputSchema,
        handler: ToolHandler,
    ) {
        let name = name.into();
        let mut tools = self.tools.write().await;
        tools.insert(name.clone(), handler);

        debug!("Registered tool: {}", name);
    }

    /// Register a resource handler
    pub async fn register_resource(&mut self, uri: impl Into<String>, handler: ResourceHandler) {
        let uri = uri.into();
        let mut resources = self.resources.write().await;
        resources.insert(uri, handler);
    }

    /// Register a prompt
    pub async fn register_prompt(
        &mut self,
        name: impl Into<String>,
        description: impl Into<String>,
        arguments: Option<Vec<PromptArgument>>,
        handler: PromptHandler,
    ) {
        let name = name.into();
        let mut prompts = self.prompts.write().await;
        prompts.insert(name, handler);
    }

    /// Check if initialized
    pub async fn is_initialized(&self) -> bool {
        *self.initialized.read().await
    }

    /// Handle an incoming request
    pub async fn handle_request(&self, request: Request) -> Result<Response> {
        trace!("Handling request: {} (id: {})", request.method, request.id);

        let result = match request.method.as_str() {
            "initialize" => self.handle_initialize(request.params).await?,
            "tools/list" => self.handle_tools_list().await?,
            "tools/call" => self.handle_tools_call(request.params).await?,
            "resources/list" => self.handle_resources_list().await?,
            "resources/read" => self.handle_resources_read(request.params).await?,
            "prompts/list" => self.handle_prompts_list().await?,
            "prompts/get" => self.handle_prompts_get(request.params).await?,
            _ => {
                return Err(anyhow!("Method not found: {}", request.method));
            }
        };

        Ok(Response {
            id: request.id,
            result: Some(result),
            error: None,
        })
    }

    async fn handle_initialize(&self, params: Option<Value>) -> Result<Value> {
        let mut initialized = self.initialized.write().await;
        if *initialized {
            return Err(anyhow!("Already initialized"));
        }

        if let Some(params) = params {
            debug!("Initialize params: {}", params);
        }

        *initialized = true;

        let result = InitializeResult {
            protocolVersion: MCP_VERSION.to_string(),
            capabilities: self.capabilities.clone(),
            serverInfo: Implementation {
                name: self.name.clone(),
                version: self.version.clone(),
            },
            instructions: Some("Reverie MCP Server - Context Engine Coding Assistant".to_string()),
        };

        Ok(json!(result))
    }

    async fn handle_tools_list(&self) -> Result<Value> {
        let tools = self.tools.read().await;

        let tool_list: Vec<Tool> = tools
            .iter()
            .map(|(name, _)| Tool {
                name: name.clone(),
                description: None,
                inputSchema: ToolInputSchema {
                    r#type: "object".to_string(),
                    properties: HashMap::new(),
                    required: Vec::new(),
                    additional: HashMap::new(),
                },
                outputSchema: None,
            })
            .collect();

        Ok(json!(ListToolsResult { tools: tool_list }))
    }

    async fn handle_tools_call(&self, params: Option<Value>) -> Result<Value> {
        let params = params.ok_or_else(|| anyhow!("Missing parameters"))?;
        let call_params: CallToolParams =
            serde_json::from_value(params).context("Invalid tool call parameters")?;

        let tools = self.tools.read().await;
        let handler = tools
            .get(&call_params.name)
            .ok_or_else(|| anyhow!("Tool not found: {}", call_params.name))?;

        let result = handler(call_params.arguments)?;
        Ok(json!(CallToolResult {
            content: vec![ToolContent::Text {
                text: result.to_string(),
            }],
            is_error: false,
        }))
    }

    async fn handle_resources_list(&self) -> Result<Value> {
        let resources = self.resources.read().await;

        let resource_list: Vec<Resource> = resources
            .iter()
            .map(|(uri, _)| Resource {
                uri: uri.clone(),
                name: uri.clone(),
                mimeType: None,
                description: None,
            })
            .collect();

        Ok(json!(ListResourcesResult {
            resources: resource_list
        }))
    }

    async fn handle_resources_read(&self, params: Option<Value>) -> Result<Value> {
        let params = params.ok_or_else(|| anyhow!("Missing parameters"))?;
        let read_params: ReadResourceParams =
            serde_json::from_value(params).context("Invalid resource read parameters")?;

        let resources = self.resources.read().await;
        let handler = resources
            .get(&read_params.uri)
            .ok_or_else(|| anyhow!("Resource not found: {}", read_params.uri))?;

        let contents = handler(&read_params.uri)?;
        Ok(json!(ReadResourceResult {
            contents: vec![contents],
        }))
    }

    async fn handle_prompts_list(&self) -> Result<Value> {
        let prompts = self.prompts.read().await;

        let prompt_list: Vec<Prompt> = prompts
            .iter()
            .map(|(name, _)| Prompt {
                name: name.clone(),
                description: None,
                arguments: None,
            })
            .collect();

        Ok(json!(ListPromptsResult {
            prompts: prompt_list
        }))
    }

    async fn handle_prompts_get(&self, params: Option<Value>) -> Result<Value> {
        let params = params.ok_or_else(|| anyhow!("Missing parameters"))?;
        let get_params: GetPromptParams =
            serde_json::from_value(params).context("Invalid prompt get parameters")?;

        let prompts = self.prompts.read().await;
        let handler = prompts
            .get(&get_params.name)
            .ok_or_else(|| anyhow!("Prompt not found: {}", get_params.name))?;

        let result = handler(&get_params.name, get_params.arguments)?;
        Ok(json!(result))
    }

    /// Start the server with stdio transport
    pub async fn run_stdio(&mut self) -> Result<()> {
        info!("Starting MCP server '{}' via stdio", self.name);

        let stdin = tokio::io::stdin();
        let stdout = tokio::io::stdout();

        let mut reader = tokio::io::BufReader::new(stdin);
        let mut writer = stdout;

        let mut line = String::new();
        loop {
            line.clear();
            let bytes_read = reader.read_line(&mut line).await?;

            if bytes_read == 0 {
                info!("EOF received, shutting down");
                break;
            }

            let request: Request =
                serde_json::from_str(&line).context("Failed to parse request")?;

            debug!("Received request: {} (id: {})", request.method, request.id);

            match self.handle_request(request).await {
                Ok(response) => {
                    let response_json = serde_json::to_string(&response)?;
                    writer.write_all(response_json.as_bytes()).await?;
                    writer.write_all(b"\n").await?;
                    writer.flush().await?;
                }
                Err(e) => {
                    error!("Error handling request: {}", e);
                    let error_response = Response {
                        id: "unknown".to_string(),
                        result: None,
                        error: Some(ErrorData {
                            code: error_codes::INTERNAL_ERROR,
                            message: e.to_string(),
                            data: None,
                        }),
                    };
                    let response_json = serde_json::to_string(&error_response)?;
                    writer.write_all(response_json.as_bytes()).await?;
                    writer.write_all(b"\n").await?;
                    writer.flush().await?;
                }
            }
        }

        Ok(())
    }

    /// Get server name
    pub fn name(&self) -> &str {
        &self.name
    }
}
