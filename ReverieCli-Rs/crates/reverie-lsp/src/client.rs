//! LSP å®¢æˆ·ç«¯
//!
//! å®žçŽ° LSP å®¢æˆ·ç«¯åŠŸèƒ½ï¼šåˆå§‹åŒ–ã€æ–‡æœ¬ç¼–è¾‘ã€è¯Šæ–­ç­‰

use std::sync::atomic::{AtomicU64, Ordering};
use tokio::sync::mpsc;

use crate::transport::LspTransport;
use crate::types::*;

// LSP å®¢æˆ·ç«¯é”™è¯¯
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

// LSP å®¢æˆ·ç«¯
pub struct LspClient {
    // ä¼ è¾“å±‚
    transport: LspTransport,
    // è¯·æ±‚ ID è®¡æ•°å™¨
    next_id: AtomicU64,
    // æ˜¯å¦å·²åˆå§‹åŒ–
    initialized: bool,
    // æœåŠ¡å™¨èƒ½åŠ›
    capabilities: Option<ServerCapabilities>,
    // å·¥ä½œåŒºæ ¹ç›®å½•
    root_uri: Option<String>,
    // æ‰“å¼€çš„æ–‡æ¡£
    open_documents: std::collections::HashMap<String, DocumentState>,
    // è¯Šæ–­æŽ¥æ”¶å™¨
    diagnostic_rx: Option<mpsc::Receiver<Diagnostic>>,
    // è¯Šæ–­å‘é€å™¨
}

// æ–‡æ¡£çŠ¶æ€
struct DocumentState {
    // æ–‡æ¡£ URI
    // æ–‡æ¡£ç‰ˆæœ¬
    version: i32,
    // æ–‡æ¡£å†…å®¹
    content: String,
    // è¯­è¨€ ID
}

impl LspClient {
    // åˆ›å»ºæ–°çš„ LSP å®¢æˆ·ç«¯
    pub fn new() -> Result<Self, LspClientError> {
        let transport = LspTransport::new()?;
        let (_tx, rx) = mpsc::channel(100);

        Ok(Self {
            transport,
            next_id: AtomicU64::new(1),
            initialized: false,
            capabilities: None,
            root_uri: None,
            open_documents: std::collections::HashMap::new(),
            diagnostic_rx: Some(rx),
        })
    }

    // åˆå§‹åŒ– LSP å®¢æˆ·ç«¯
    pub async fn initialize(
        &mut self,
        root_uri: &str,
        command: &str,
        args: &[&str],
    ) -> Result<(), LspClientError> {
        // å¯åŠ¨ä¼ è¾“å±‚
        self.transport.start(command, args)?;

        // å‡†å¤‡åˆå§‹åŒ–å‚æ•°
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

        // å‘é€åˆå§‹åŒ–è¯·æ±‚
        let request = Request {
            jsonrpc: "2.0".to_string(),
            id: self.next_id(),
            method: "initialize".to_string(),
            params: Some(
                serde_json::to_value(&params)
                    .map_err(|e| LspClientError::ParseError(e.to_string()))?,
            ),
        };

        // å‘é€è¯·æ±‚å¹¶ç­‰å¾…å“åº”
        self.transport.send_request(request)?;

        // è¿™é‡Œåº”è¯¥ç­‰å¾…å“åº”å¹¶è§£æž
        // ç®€åŒ–å¤„ç†
        self.initialized = true;
        self.root_uri = Some(root_uri.to_string());

        // å‘é€ initialized é€šçŸ¥
        let notification = Notification {
            jsonrpc: "2.0".to_string(),
            method: "initialized".to_string(),
            params: None,
        };
        self.transport.send_notification(notification)?;

        Ok(())
    }

    // æ‰“å¼€æ–‡æœ¬æ–‡æ¡£
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
            version,
            content: text.to_string(),
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

    // æ›´æ”¹æ–‡æœ¬æ–‡æ¡£
    pub fn did_change(
        &mut self,
        uri: &str,
        version: i32,
        changes: Vec<TextDocumentContentChangeEvent>,
    ) -> Result<(), LspClientError> {
        if !self.initialized {
            return Err(LspClientError::NotInitialized);
        }

        // æ›´æ–°æœ¬åœ°æ–‡æ¡£çŠ¶æ€
        if let Some(doc) = self.open_documents.get_mut(uri) {
            doc.version = version;
            for change in &changes {
                if let Some(_range) = &change.range {
                    // ç®€åŒ–å¤„ç†ï¼šç›´æŽ¥æ›¿æ¢
                    doc.content = change.text.clone();
                } else {
                    doc.content = change.text.clone();
                }
            }
        }

        let _params = VersionedTextDocumentIdentifier {
            uri: uri.to_string(),
            version: Some(version),
        };

        // è¿™é‡Œåº”è¯¥å‘é€æ­£ç¡®çš„ didChange é€šçŸ¥
        // ç®€åŒ–å¤„ç†
        Ok(())
    }

    // å…³é—­æ–‡æœ¬æ–‡æ¡£
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

    // ä¿å­˜æ–‡æœ¬æ–‡æ¡£
    pub fn did_save(&mut self, uri: &str, _text: Option<&str>) -> Result<(), LspClientError> {
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

    // èŽ·å–è¯Šæ–­
    pub async fn get_diagnostics(&mut self, _uri: &str) -> Result<Vec<Diagnostic>, LspClientError> {
        if !self.initialized {
            return Err(LspClientError::NotInitialized);
        }

        // è¿™é‡Œåº”è¯¥è¯·æ±‚è¯Šæ–­
        // ç®€åŒ–å¤„ç†ï¼šè¿”å›žç©ºåˆ—è¡¨
        Ok(vec![])
    }

    // èŽ·å–è¯Šæ–­æµ
    pub fn diagnostic_stream(&mut self) -> Option<mpsc::Receiver<Diagnostic>> {
        self.diagnostic_rx.take()
    }

    // èŽ·å–æœåŠ¡å™¨èƒ½åŠ›
    pub fn capabilities(&self) -> Option<&ServerCapabilities> {
        self.capabilities.as_ref()
    }

    // æ£€æŸ¥æ˜¯å¦å·²åˆå§‹åŒ–
    pub fn is_initialized(&self) -> bool {
        self.initialized
    }

    // èŽ·å–ä¸‹ä¸€ä¸ªè¯·æ±‚ ID
    fn next_id(&self) -> u64 {
        self.next_id.fetch_add(1, Ordering::SeqCst)
    }

    // åœæ­¢ LSP å®¢æˆ·ç«¯
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

        // å‘é€ exit é€šçŸ¥
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
