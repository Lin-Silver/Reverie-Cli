//! Transport layer for MCP communication.
//!
//! Supports stdio-based communication with MCP servers.

use crate::types::*;
use anyhow::{anyhow, Context, Result};
use serde_json::Value;
use std::collections::HashMap;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt};
use tokio::process::{Child, Command};
use tracing::{debug, info, trace};

/// Transport trait for MCP communication
#[async_trait::async_trait]
pub trait Transport: Send + Sync {
    /// Send a request and wait for response
    async fn send_request(&mut self, request: Request) -> Result<Response>;
    /// Close the transport
    async fn close(&mut self) -> Result<()>;
}

/// Stdio transport for communicating with MCP servers via stdin/stdout
pub struct StdioTransport {
    /// Child process handle
    child: Option<Child>,
    /// stdin writer
    stdin: Option<tokio::process::ChildStdin>,
    /// stdout reader
    stdout: Option<tokio::io::BufReader<tokio::process::ChildStdout>>,
}

impl StdioTransport {
    /// Spawn a new MCP server process and establish stdio connection
    pub fn spawn(command: &str, args: &[String], env: &HashMap<String, String>) -> Result<Self> {
        info!("Spawning MCP server: {} {:?}", command, args);

        let mut cmd = Command::new(command);
        cmd.args(args);

        // Add environment variables
        for (key, value) in env {
            cmd.env(key, value);
        }

        // Configure stdio
        cmd.stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped());

        // Spawn the process
        let mut child = cmd
            .spawn()
            .with_context(|| format!("Failed to spawn MCP server: {}", command))?;

        info!("MCP server spawned with PID: {:?}", child.id());

        // Split stdin and stdout
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| anyhow!("Failed to take stdin"))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| anyhow!("Failed to take stdout"))?;

        let stdout = tokio::io::BufReader::new(stdout);

        Ok(Self {
            child: Some(child),
            stdin: Some(stdin),
            stdout: Some(stdout),
        })
    }

    /// Read a single JSON message from stdout
    async fn read_message(&mut self) -> Result<Value> {
        let stdout = self
            .stdout
            .as_mut()
            .ok_or_else(|| anyhow!("No stdout available"))?;

        let mut line = String::new();
        stdout
            .read_line(&mut line)
            .await
            .context("Failed to read from MCP server")?;

        if line.is_empty() {
            return Err(anyhow!("EOF from MCP server"));
        }

        trace!("Received: {}", line.trim());

        serde_json::from_str(&line).context("Failed to parse JSON from MCP server")
    }

    /// Write a JSON message to stdin
    async fn write_message(&mut self, message: &Value) -> Result<()> {
        let stdin = self
            .stdin
            .as_mut()
            .ok_or_else(|| anyhow!("No stdin available"))?;

        let json = serde_json::to_string(message)?;
        debug!("Sending: {}", json);

        stdin.write_all(json.as_bytes()).await?;
        stdin.write_all(b"\n").await?;
        stdin.flush().await?;

        Ok(())
    }
}

#[async_trait::async_trait]
impl Transport for StdioTransport {
    async fn send_request(&mut self, request: Request) -> Result<Response> {
        let request_value = serde_json::to_value(&request)?;
        self.write_message(&request_value).await?;

        let response_value = self.read_message().await?;
        let response: Response =
            serde_json::from_value(response_value).context("Failed to parse response")?;

        Ok(response)
    }

    async fn close(&mut self) -> Result<()> {
        info!("Closing stdio transport");

        if let Some(mut child) = self.child.take() {
            // Send SIGTERM to the process
            child
                .kill()
                .await
                .context("Failed to kill MCP server process")?;
        }

        self.stdin = None;
        self.stdout = None;

        Ok(())
    }
}
