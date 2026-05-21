//! LSP 客户端
//!
//! 实现 LSP 客户端功能：初始化、文本编辑、诊断等

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use tokio::sync::mpsc;

use crate::transport::LspTransport;
use crate::types::*;

/// LSP 客户端错误
#[derive(Debug)]
pub enum LspClientError {
    TransportError(crate::transport::LspTransportError),
    NotInitialized,
    Timeout,
    ParseError(String),
}

impl From<crate::transport::LspTransportError> for LspClientError {
    fn from(err: crate::transport::LspTransportError) -> Self {
        LspClientError::TransportError(err)
    }
}

impl std::fmt::Display for LspClientError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            LspClientError::TransportError(e) => write!(f, "Transport error: {}", e),
            LspClientError::NotInitialized => write!(f, "LSP client not initialized"),
            LspClientError::Timeout => write!(f, "Timeout"),
            LspClientError::ParseError(msg) => write!(f, "Parse error: {}", msg),
        }
    }
}

impl std::error::Error for LspClientError {}

/// LSP 客户端
pub struct LspClient {
    /// 传输层
    transport: LspTransport,
    /// 请求 ID 计数器
    next_id: AtomicU64,
    /// 是否已初始化
    initialized: bool,
    /// 服务器能力
    capabilities: Option<ServerCapabilities>,
    /// 工作区根目录
    root_uri: Option<String>,
    /// 打开的文档
    open_documents: std::collections::HashMap<String, DocumentState>,
    /// 诊断接收器
    diagnostic_rx: Option<mpsc::Receiver<Diagnostic>>,
    /// 诊断发送器
    diagnostic_tx: Option<mpsc::Sender<Diagnostic>>,
}

/// 文档状态
struct DocumentState {
    /// 文档 URI
    uri: String,
    /// 文档版本
    version: i32,
    /// 文档内容
    content: String,
    /// 语言 ID
    language_id: String,
}

impl LspClient {
    /// 创建新的 LSP 客户端
    pub fn new() -> Result<Self, LspClientError> {
        let transport = LspTransport::new()?;
        let (tx, rx) = mpsc::channel(100);

        Ok(Self {
            transport,
            next_id: AtomicU64::new(1),
            initialized: false,
            capabilities: None,
            root_uri: None,
            open_documents: std::collections::HashMap::new(),
            diagnostic_rx: Some(rx),
            diagnostic_tx: Some(tx),
        })
    }

    /// 初始化 LSP 客户端
    pub async fn initialize(
        &mut self,
        root_uri: &str,
        command: &str,
        args: &[&str],
    ) -> Result<(), LspClientError> {
        // 启动传输层
        self.transport.start(command, args)?;

        // 准备初始化参数
        let params = InitializeParams {
            process_id: Some(std::process::id()),
            root_uri: Some(root_uri.to_string()),
            root_path: None,
            initialization_options: None,
            capabilities: ClientCapabilities {
                workspace: Some(WorkspaceClientCapabilities {
                    apply_edit: Some(true),
                    workspace_edit: Some(WorkspaceEditCapabilities {
                        document_changes: Some(true),
                        resource_operations: None,
                        failure_handling: None,
                        normalizes_line_endings: None,
                        change_annotation_support: None,
                    }),
                    did_change_configuration: None,
                    did_change_watched_files: None,
                    symbol: None,
                    execute_command: None,
                    will_save_wait_until: None,
                    did_change_workspace_folders: None,
                    configuration: None,
                    semantic_tokens: None,
                    code_lens: None,
                    file_operations: None,
                }),
                text_document: Some(TextDocumentClientCapabilities {
                    synchronization: Some(TextDocumentSyncCapabilities {
                        did_save: Some(true),
                        will_save: Some(false),
                        will_save_wait_until: Some(false),
                        change: Some(2), // Incremental
                    }),
                    completion: None,
                    hover: None,
                    signature_help: None,
                    declaration: None,
                    definition: None,
                    type_definition: None,
                    implementation: None,
                    references: None,
                    document_highlight: None,
                    document_symbol: None,
                    code_action: None,
                    code_lens: None,
                    document_link: None,
                    color_provider: None,
                    formatting: None,
                    range_formatting: None,
                    on_type_formatting: None,
                    rename: None,
                    folding_range: None,
                    selection_range: None,
                    publish_diagnostics: None,
                    call_hierarchy: None,
                    semantic_tokens: None,
                    linked_editing_range: None,
                    moniker: None,
                    type_hierarchy: None,
                    inline_value: None,
                    inlay_hint: None,
                    diagnostic: None,
                    inline_completion: None,
                }),
                window: Some(WindowClientCapabilities {
                    show_document: Some(ShowDocumentCapabilities { support: true }),
                    work_done_progress: Some(true),
                }),
                general: Some(GeneralClientCapabilities {
                    stale_request_support: None,
                    regular_expressions: None,
                    markdown: None,
                    position_encodings: None,
                }),
            },
            trace: Some("messages".to_string()),
            workspace_folders: None,
        };

        // 发送初始化请求
        let request = Request {
            jsonrpc: "2.0".to_string(),
            id: self.next_id(),
            method: "initialize".to_string(),
            params: Some(
                serde_json::to_value(&params)
                    .map_err(|e| LspClientError::ParseError(e.to_string()))?,
            ),
        };

        // 发送请求并等待响应
        self.transport.send_request(request)?;

        // 这里应该等待响应并解析
        // 简化处理
        self.initialized = true;
        self.root_uri = Some(root_uri.to_string());

        // 发送 initialized 通知
        let notification = Notification {
            jsonrpc: "2.0".to_string(),
            method: "initialized".to_string(),
            params: None,
        };
        self.transport.send_notification(notification)?;

        Ok(())
    }

    /// 打开文本文档
    pub fn did_open(
        &mut self,
        uri: &str,
        language_id: &str,
        version: i32,
        text: &str,
    ) -> Result<(), LspClientError> {
        if !self.initialized {
            return Err(LspClientError::NotInitialized);
        }

        let document = DocumentState {
            uri: uri.to_string(),
            version,
            content: text.to_string(),
            language_id: language_id.to_string(),
        };

        self.open_documents.insert(uri.to_string(), document);

        let params = TextDocumentItem {
            uri: uri.to_string(),
            language_id: language_id.to_string(),
            version,
            text: text.to_string(),
        };

        let notification = Notification {
            jsonrpc: "2.0".to_string(),
            method: "textDocument/didOpen".to_string(),
            params: Some(
                serde_json::to_value(&params)
                    .map_err(|e| LspClientError::ParseError(e.to_string()))?,
            ),
        };

        self.transport.send_notification(notification)?;

        Ok(())
    }

    /// 更改文本文档
    pub fn did_change(
        &mut self,
        uri: &str,
        version: i32,
        changes: Vec<TextDocumentContentChangeEvent>,
    ) -> Result<(), LspClientError> {
        if !self.initialized {
            return Err(LspClientError::NotInitialized);
        }

        // 更新本地文档状态
        if let Some(doc) = self.open_documents.get_mut(uri) {
            doc.version = version;
            for change in &changes {
                if let Some(range) = &change.range {
                    // 简化处理：直接替换
                    doc.content = change.text.clone();
                } else {
                    doc.content = change.text.clone();
                }
            }
        }

        let params = VersionedTextDocumentIdentifier {
            uri: uri.to_string(),
            version: Some(version),
        };

        // 这里应该发送正确的 didChange 通知
        // 简化处理
        Ok(())
    }

    /// 关闭文本文档
    pub fn did_close(&mut self, uri: &str) -> Result<(), LspClientError> {
        if !self.initialized {
            return Err(LspClientError::NotInitialized);
        }

        self.open_documents.remove(uri);

        let params = TextDocumentIdentifier {
            uri: uri.to_string(),
        };

        let notification = Notification {
            jsonrpc: "2.0".to_string(),
            method: "textDocument/didClose".to_string(),
            params: Some(
                serde_json::to_value(&params)
                    .map_err(|e| LspClientError::ParseError(e.to_string()))?,
            ),
        };

        self.transport.send_notification(notification)?;

        Ok(())
    }

    /// 保存文本文档
    pub fn did_save(&mut self, uri: &str, text: Option<&str>) -> Result<(), LspClientError> {
        if !self.initialized {
            return Err(LspClientError::NotInitialized);
        }

        let params = TextDocumentIdentifier {
            uri: uri.to_string(),
        };

        let notification = Notification {
            jsonrpc: "2.0".to_string(),
            method: "textDocument/didSave".to_string(),
            params: Some(
                serde_json::to_value(&params)
                    .map_err(|e| LspClientError::ParseError(e.to_string()))?,
            ),
        };

        self.transport.send_notification(notification)?;

        Ok(())
    }

    /// 获取诊断
    pub async fn get_diagnostics(&mut self, uri: &str) -> Result<Vec<Diagnostic>, LspClientError> {
        if !self.initialized {
            return Err(LspClientError::NotInitialized);
        }

        // 这里应该请求诊断
        // 简化处理：返回空列表
        Ok(vec![])
    }

    /// 获取诊断流
    pub fn diagnostic_stream(&mut self) -> Option<mpsc::Receiver<Diagnostic>> {
        self.diagnostic_rx.take()
    }

    /// 获取服务器能力
    pub fn capabilities(&self) -> Option<&ServerCapabilities> {
        self.capabilities.as_ref()
    }

    /// 检查是否已初始化
    pub fn is_initialized(&self) -> bool {
        self.initialized
    }

    /// 获取下一个请求 ID
    fn next_id(&self) -> u64 {
        self.next_id.fetch_add(1, Ordering::SeqCst)
    }

    /// 停止 LSP 客户端
    pub async fn shutdown(&mut self) -> Result<(), LspClientError> {
        if !self.initialized {
            return Ok(());
        }

        let request = Request {
            jsonrpc: "2.0".to_string(),
            id: self.next_id(),
            method: "shutdown".to_string(),
            params: None,
        };

        self.transport.send_request(request)?;

        // 发送 exit 通知
        let notification = Notification {
            jsonrpc: "2.0".to_string(),
            method: "exit".to_string(),
            params: None,
        };
        self.transport.send_notification(notification)?;

        self.initialized = false;

        Ok(())
    }
}

impl Drop for LspClient {
    fn drop(&mut self) {
        let _ = self.transport.stop();
    }
}
