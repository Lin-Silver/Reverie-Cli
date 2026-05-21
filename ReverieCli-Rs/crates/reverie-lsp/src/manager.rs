//! LSP 管理器
//!
//! 管理多个 LSP 服务器实例，支持自动启动、停止和配置

use crate::client::LspClient;
use crate::types::*;
use std::collections::HashMap;
use std::path::Path;

/// LSP 服务器配置
#[derive(Debug, Clone)]
pub struct LspServerConfig {
    /// 服务器名称
    pub name: String,
    /// 服务器命令
    pub command: String,
    /// 服务器参数
    pub args: Vec<String>,
    /// 工作区根目录
    pub root_uri: Option<String>,
    /// 支持的文件模式
    pub file_patterns: Vec<String>,
    /// 语言 ID
    pub language_id: String,
    /// 是否自动启动
    pub auto_start: bool,
    /// 启动延迟（毫秒）
    pub start_delay_ms: u64,
}

impl Default for LspServerConfig {
    fn default() -> Self {
        Self {
            name: "default".to_string(),
            command: "".to_string(),
            args: vec![],
            root_uri: None,
            file_patterns: vec![],
            language_id: "".to_string(),
            auto_start: false,
            start_delay_ms: 0,
        }
    }
}

/// LSP 服务器状态
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LspServerState {
    /// 未启动
    Stopped,
    /// 启动中
    Starting,
    /// 已启动
    Running,
    /// 停止中
    Stopping,
    /// 错误
    Error,
}

/// LSP 服务器信息
#[derive(Debug, Clone)]
pub struct LspServerInfo {
    /// 配置
    pub config: LspServerConfig,
    /// 状态
    pub state: LspServerState,
    /// 启动时间
    pub started_at: Option<u64>,
    /// 错误信息
    pub error: Option<String>,
}

/// LSP 管理器
pub struct LspManager {
    /// 服务器配置
    servers: HashMap<String, LspServerInfo>,
    /// LSP 客户端
    clients: HashMap<String, LspClient>,
    /// 文件到服务器的映射
    file_to_server: HashMap<String, String>,
    /// 工作区根目录
    workspace_root: Option<String>,
    /// 配置路径
    config_path: Option<String>,
}

impl LspManager {
    /// 创建新的 LSP 管理器
    pub fn new() -> Self {
        Self {
            servers: HashMap::new(),
            clients: HashMap::new(),
            file_to_server: HashMap::new(),
            workspace_root: None,
            config_path: None,
        }
    }

    /// 设置工作区根目录
    pub fn set_workspace_root(&mut self, root: &str) {
        self.workspace_root = Some(root.to_string());
    }

    /// 设置配置路径
    pub fn set_config_path(&mut self, path: &str) {
        self.config_path = Some(path.to_string());
    }

    /// 添加服务器配置
    pub fn add_server(&mut self, config: LspServerConfig) {
        let name = config.name.clone();
        self.servers.insert(
            name.clone(),
            LspServerInfo {
                config: config.clone(),
                state: LspServerState::Stopped,
                started_at: None,
                error: None,
            },
        );

        // 注册文件模式映射
        for pattern in &config.file_patterns {
            self.file_to_server.insert(pattern.clone(), name.clone());
        }
    }

    /// 获取服务器配置
    pub fn get_server(&self, name: &str) -> Option<&LspServerInfo> {
        self.servers.get(name)
    }

    /// 获取服务器配置（可变）
    pub fn get_server_mut(&mut self, name: &str) -> Option<&mut LspServerInfo> {
        self.servers.get_mut(name)
    }

    /// 列出所有服务器
    pub fn list_servers(&self) -> Vec<&LspServerInfo> {
        self.servers.values().collect()
    }

    /// 启动服务器
    pub async fn start_server(&mut self, name: &str) -> Result<(), String> {
        let config = match self.servers.get(name) {
            Some(info) => info.config.clone(),
            None => return Err(format!("Server '{}' not found", name)),
        };

        // 更新状态
        if let Some(info) = self.servers.get_mut(name) {
            info.state = LspServerState::Starting;
        }

        // 创建 LSP 客户端
        let mut client = LspClient::new().map_err(|e| e.to_string())?;

        // 获取工作区根目录
        let root_uri = config
            .root_uri
            .clone()
            .or_else(|| self.workspace_root.clone().map(|r| format!("file://{}", r)));

        if let Some(root) = root_uri {
            // 启动 LSP 服务器
            client
                .initialize(
                    &root,
                    &config.command,
                    &config.args.iter().map(|s| s.as_str()).collect::<Vec<_>>(),
                )
                .await
                .map_err(|e| e.to_string())?;

            // 更新状态
            if let Some(info) = self.servers.get_mut(name) {
                info.state = LspServerState::Running;
                info.started_at = Some(
                    std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .unwrap_or_default()
                        .as_millis() as u64,
                );
            }

            // 保存客户端
            self.clients.insert(name.to_string(), client);
        } else {
            return Err("No workspace root available".to_string());
        }

        Ok(())
    }

    /// 停止服务器
    pub async fn stop_server(&mut self, name: &str) -> Result<(), String> {
        // 更新状态
        if let Some(info) = self.servers.get_mut(name) {
            info.state = LspServerState::Stopping;
        }

        // 停止 LSP 客户端
        if let Some(client) = self.clients.remove(name) {
            // 这里应该调用 client.shutdown()
            // 简化处理
        }

        // 更新状态
        if let Some(info) = self.servers.get_mut(name) {
            info.state = LspServerState::Stopped;
        }

        Ok(())
    }

    /// 重启服务器
    pub async fn restart_server(&mut self, name: &str) -> Result<(), String> {
        self.stop_server(name).await?;
        tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
        self.start_server(name).await?;
        Ok(())
    }

    /// 启动所有自动启动的服务器
    pub async fn start_all(&mut self) -> Result<(), String> {
        let names: Vec<String> = self
            .servers
            .iter()
            .filter_map(|(name, info)| {
                (info.config.auto_start && info.state == LspServerState::Stopped)
                    .then(|| name.clone())
            })
            .collect();
        for name in names {
            self.start_server(&name).await?;
        }
        Ok(())
    }

    /// 停止所有服务器
    pub async fn stop_all(&mut self) -> Result<(), String> {
        for name in self.servers.keys().cloned().collect::<Vec<_>>() {
            self.stop_server(&name).await?;
        }
        Ok(())
    }

    /// 获取适用于文件的服务器
    pub fn get_server_for_file(&self, file_path: &str) -> Option<&str> {
        // 简化处理：直接匹配
        for (pattern, server) in &self.file_to_server {
            if file_path.contains(pattern) {
                return Some(server);
            }
        }
        None
    }

    /// 通知文件打开
    pub async fn did_open(
        &mut self,
        file_path: &str,
        language_id: &str,
        text: &str,
    ) -> Result<(), String> {
        let server_name = match self.get_server_for_file(file_path) {
            Some(name) => name.to_string(),
            None => return Ok(()), // 没有匹配的服务器
        };

        let client = match self.clients.get_mut(&server_name) {
            Some(client) => client,
            None => return Err(format!("Server '{}' not running", server_name)),
        };

        let uri = format!("file://{}", file_path);
        let version = 1i32;

        client
            .did_open(&uri, language_id, version, text)
            .map_err(|e| e.to_string())?;

        Ok(())
    }

    /// 通知文件更改
    pub async fn did_change(
        &mut self,
        file_path: &str,
        version: i32,
        changes: Vec<TextDocumentContentChangeEvent>,
    ) -> Result<(), String> {
        let server_name = match self.get_server_for_file(file_path) {
            Some(name) => name.to_string(),
            None => return Ok(()),
        };

        let client = match self.clients.get_mut(&server_name) {
            Some(client) => client,
            None => return Err(format!("Server '{}' not running", server_name)),
        };

        let uri = format!("file://{}", file_path);

        client
            .did_change(&uri, version, changes)
            .map_err(|e| e.to_string())?;

        Ok(())
    }

    /// 通知文件关闭
    pub async fn did_close(&mut self, file_path: &str) -> Result<(), String> {
        let server_name = match self.get_server_for_file(file_path) {
            Some(name) => name.to_string(),
            None => return Ok(()),
        };

        let client = match self.clients.get_mut(&server_name) {
            Some(client) => client,
            None => return Err(format!("Server '{}' not running", server_name)),
        };

        let uri = format!("file://{}", file_path);

        client.did_close(&uri).map_err(|e| e.to_string())?;

        Ok(())
    }

    /// 通知文件保存
    pub async fn did_save(&mut self, file_path: &str) -> Result<(), String> {
        let server_name = match self.get_server_for_file(file_path) {
            Some(name) => name.to_string(),
            None => return Ok(()),
        };

        let client = match self.clients.get_mut(&server_name) {
            Some(client) => client,
            None => return Err(format!("Server '{}' not running", server_name)),
        };

        let uri = format!("file://{}", file_path);

        client.did_save(&uri, None).map_err(|e| e.to_string())?;

        Ok(())
    }

    /// 获取诊断
    pub async fn get_diagnostics(&mut self, file_path: &str) -> Result<Vec<Diagnostic>, String> {
        let server_name = match self.get_server_for_file(file_path) {
            Some(name) => name.to_string(),
            None => return Ok(vec![]),
        };

        let client = match self.clients.get_mut(&server_name) {
            Some(client) => client,
            None => return Err(format!("Server '{}' not running", server_name)),
        };

        let uri = format!("file://{}", file_path);

        client
            .get_diagnostics(&uri)
            .await
            .map_err(|e| e.to_string())
    }

    /// 加载配置
    pub fn load_config(&mut self, path: &str) -> Result<(), String> {
        // 简化处理：实际应该从 JSON 文件加载
        Ok(())
    }

    /// 保存配置
    pub fn save_config(&self, path: &str) -> Result<(), String> {
        // 简化处理：实际应该保存到 JSON 文件
        Ok(())
    }
}

impl Default for LspManager {
    fn default() -> Self {
        Self::new()
    }
}
