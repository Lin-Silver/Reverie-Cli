//! MCP (Model Context Protocol) client and server implementation for Reverie CLI.
//!
//! This module provides:
//! - MCP client for connecting to external tool servers
//! - MCP server for exposing Reverie capabilities to orchestrating agents
//! - Resource discovery and tool invocation
//! - Server lifecycle management
//!
//! Based on the Model Context Protocol specification:
//! https://modelcontextprotocol.io/specification

pub mod client;
pub mod registry;
pub mod server;
pub mod transport;
pub mod types;

pub use client::McpClient;
pub use registry::McpRegistry;
pub use server::McpServer;
pub use types::*;
