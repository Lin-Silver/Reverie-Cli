//! MCP Registry for managing multiple MCP servers.
//!
//! The registry handles discovery, loading, and lifecycle management of MCP servers.

use crate::client::McpClient;
use crate::types::*;
use anyhow::{anyhow, Context, Result};
use serde_json::Value;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use tokio::sync::RwLock;
use tracing::{debug, error, info, warn};

/// Registry entry for an MCP server
pub struct RegistryEntry {
    /// Server configuration
    pub config: McpServerConfig,
    /// Client instance
    pub client: Option<McpClient>,
    /// Status
    pub status: McpServerStatus,
}

/// MCP Registry for managing multiple MCP servers
pub struct McpRegistry {
    /// Server configurations
    servers: RwLock<HashMap<String, RegistryEntry>>,
    /// Configuration file path
    config_path: Option<PathBuf>,
    /// Project root
    project_root: PathBuf,
}

impl McpRegistry {
    /// Create a new MCP registry
    pub fn new(project_root: impl AsRef<Path>) -> Self {
        Self {
            servers: RwLock::new(HashMap::new()),
            config_path: None,
            project_root: project_root.as_ref().to_path_buf(),
        }
    }

    /// Set the configuration file path
    pub fn with_config_path(mut self, path: impl AsRef<Path>) -> Self {
        self.config_path = Some(path.as_ref().to_path_buf());
        self
    }

    /// Add a server to the registry
    pub async fn add_server(&mut self, config: McpServerConfig) -> Result<()> {
        let name = config.name.clone();

        if !config.enabled {
            debug!("Skipping disabled server: {}", name);
            return Ok(());
        }

        let client = McpClient::new(config.clone());
        let status = client.status();

        let entry = RegistryEntry {
            config,
            client: Some(client),
            status,
        };

        self.servers.write().await.insert(name, entry);

        Ok(())
    }

    /// Remove a server from the registry
    pub async fn remove_server(&mut self, name: &str) -> Result<()> {
        if let Some(entry) = self.servers.write().await.remove(name) {
            if let Some(mut client) = entry.client {
                let _ = client.disconnect().await;
            }
            info!("Removed MCP server: {}", name);
        }
        Ok(())
    }

    /// Connect to a server
    pub async fn connect(&mut self, name: &str) -> Result<()> {
        let mut servers = self.servers.write().await;

        let entry = servers
            .get_mut(name)
            .ok_or_else(|| anyhow!("Server not found: {}", name))?;

        if let Some(client) = &mut entry.client {
            client.connect().await?;
            entry.status = client.status();
        }

        Ok(())
    }

    /// Initialize a server
    pub async fn initialize(&mut self, name: &str) -> Result<InitializeResult> {
        let mut servers = self.servers.write().await;

        let entry = servers
            .get_mut(name)
            .ok_or_else(|| anyhow!("Server not found: {}", name))?;

        if let Some(client) = &mut entry.client {
            let result = client.initialize().await?;
            entry.status = client.status();
            Ok(result)
        } else {
            Err(anyhow!("No client for server: {}", name))
        }
    }

    /// Connect and initialize all servers
    pub async fn initialize_all(&mut self) -> Result<Vec<(String, InitializeResult)>> {
        let mut results = Vec::new();
        let server_names: Vec<String> = self.servers.read().await.keys().cloned().collect();

        for name in server_names {
            match self.initialize(&name).await {
                Ok(result) => {
                    results.push((name, result));
                }
                Err(e) => {
                    error!("Failed to initialize server {}: {}", name, e);
                }
            }
        }

        Ok(results)
    }

    /// Call a tool from a server
    pub async fn call_tool(
        &self,
        server_name: &str,
        tool_name: &str,
        arguments: HashMap<String, Value>,
    ) -> Result<CallToolResult> {
        let servers = self.servers.read().await;

        let entry = servers
            .get(server_name)
            .ok_or_else(|| anyhow!("Server not found: {}", server_name))?;

        if let Some(client) = &entry.client {
            client.call_tool(tool_name, arguments).await
        } else {
            Err(anyhow!("No client for server: {}", server_name))
        }
    }

    /// Call a tool from any available server
    pub async fn call_tool_any(
        &self,
        tool_name: &str,
        arguments: HashMap<String, Value>,
    ) -> Result<(String, CallToolResult)> {
        let servers = self.servers.read().await;

        for (name, entry) in servers.iter() {
            if let Some(client) = &entry.client {
                match client.call_tool(tool_name, arguments.clone()).await {
                    Ok(result) => return Ok((name.clone(), result)),
                    Err(e) => {
                        debug!("Tool {} not available on {}: {}", tool_name, name, e);
                    }
                }
            }
        }

        Err(anyhow!("Tool '{}' not found in any server", tool_name))
    }

    /// List all tools from all servers
    pub async fn list_all_tools(&self) -> Result<HashMap<String, Vec<Tool>>> {
        let servers = self.servers.read().await;
        let mut all_tools = HashMap::new();

        for (name, entry) in servers.iter() {
            if let Some(client) = &entry.client {
                match client.list_tools().await {
                    Ok(tools) => {
                        all_tools.insert(name.clone(), tools);
                    }
                    Err(e) => {
                        error!("Failed to list tools from {}: {}", name, e);
                    }
                }
            }
        }

        Ok(all_tools)
    }

    /// List all servers
    pub async fn list_servers(&self) -> Vec<McpServerStatus> {
        let servers = self.servers.read().await;
        servers.values().map(|e| e.status.clone()).collect()
    }

    /// Get server status
    pub async fn get_status(&self, name: &str) -> Option<McpServerStatus> {
        let servers = self.servers.read().await;
        servers.get(name).map(|entry| entry.status.clone())
    }

    /// Disconnect from all servers
    pub async fn disconnect_all(&mut self) -> Result<()> {
        let server_names: Vec<String> = self.servers.read().await.keys().cloned().collect();

        for name in server_names {
            if let Some(entry) = self.servers.write().await.get_mut(&name) {
                if let Some(mut client) = entry.client.take() {
                    let _ = client.disconnect().await;
                }
                entry.status = McpServerStatus {
                    name: name.clone(),
                    running: false,
                    initialized: false,
                    tool_count: 0,
                    resource_count: 0,
                    prompt_count: 0,
                    last_error: None,
                };
            }
        }

        Ok(())
    }

    /// Get the project root
    pub fn project_root(&self) -> &Path {
        &self.project_root
    }
}
