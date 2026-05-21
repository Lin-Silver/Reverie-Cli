//! LSP 类型定义
//! 
//! 定义语言服务器协议的核心类型

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// LSP 版本
pub const LSP_VERSION: &str = "3.17.0";

/// 位置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Position {
    pub line: u32,
    pub character: u32,
}

/// 范围
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Range {
    pub start: Position,
    pub end: Position,
}

/// 文本文档定位器
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextDocumentIdentifier {
    pub uri: String,
}

/// 文本文档定位器（带版本）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextDocumentItem {
    pub uri: String,
    pub language_id: String,
    pub version: i32,
    pub text: String,
}

/// 文本文档定位器（带版本）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VersionedTextDocumentIdentifier {
    pub uri: String,
    pub version: Option<i32>,
}

/// 文本文档内容变化
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextDocumentContentChangeEvent {
    pub range: Option<Range>,
    pub range_length: Option<u32>,
    pub text: String,
}

/// 文本文档定位参数
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextDocumentPositionParams {
    pub text_document: TextDocumentIdentifier,
    pub position: Position,
}

/// 初始化参数
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InitializeParams {
    pub process_id: Option<u32>,
    pub root_uri: Option<String>,
    pub root_path: Option<String>,
    pub initialization_options: Option<serde_json::Value>,
    pub capabilities: ClientCapabilities,
    pub trace: Option<String>,
    pub workspace_folders: Option<Vec<WorkspaceFolder>>,
}

/// 客户端能力
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClientCapabilities {
    pub workspace: Option<WorkspaceClientCapabilities>,
    pub text_document: Option<TextDocumentClientCapabilities>,
    pub window: Option<WindowClientCapabilities>,
    pub general: Option<GeneralClientCapabilities>,
}

/// 工作区客户端能力
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkspaceClientCapabilities {
    pub apply_edit: Option<bool>,
    pub workspace_edit: Option<WorkspaceEditCapabilities>,
    pub did_change_configuration: Option<DidChangeConfigurationClientCapabilities>,
    pub did_change_watched_files: Option<DidChangeWatchedFilesClientCapabilities>,
    pub symbol: Option<WorkspaceSymbolClientCapabilities>,
    pub execute_command: Option<ExecuteCommandClientCapabilities>,
    pub will_save_wait_until: Option<bool>,
    pub did_change_workspace_folders: Option<DidChangeWorkspaceFoldersClientCapabilities>,
    pub configuration: Option<bool>,
    pub semantic_tokens: Option<SemanticTokensWorkspaceClientCapabilities>,
    pub code_lens: Option<CodeLensWorkspaceClientCapabilities>,
    pub file_operations: Option<FileOperationsWorkspaceClientCapabilities>,
}

/// 工作区编辑能力
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkspaceEditCapabilities {
    pub document_changes: Option<bool>,
    pub resource_operations: Option<Vec<String>>,
    pub failure_handling: Option<String>,
    pub normalizes_line_endings: Option<bool>,
    pub change_annotation_support: Option<ChangeAnnotationSupport>,
}

/// 更改注释支持
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChangeAnnotationSupport {
    pub groups_on_label: Option<bool>,
}

/// 文本文档客户端能力
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextDocumentClientCapabilities {
    pub synchronization: Option<TextDocumentSyncCapabilities>,
    pub completion: Option<CompletionCapabilities>,
    pub hover: Option<HoverCapabilities>,
    pub signature_help: Option<SignatureHelpCapabilities>,
    pub declaration: Option<DeclarationCapabilities>,
    pub definition: Option<DefinitionCapabilities>,
    pub type_definition: Option<TypeDefinitionCapabilities>,
    pub implementation: Option<ImplementationCapabilities>,
    pub references: Option<ReferencesCapabilities>,
    pub document_highlight: Option<DocumentHighlightCapabilities>,
    pub document_symbol: Option<DocumentSymbolCapabilities>,
    pub code_action: Option<CodeActionCapabilities>,
    pub code_lens: Option<CodeLensCapabilities>,
    pub document_link: Option<DocumentLinkCapabilities>,
    pub color_provider: Option<ColorProviderCapabilities>,
    pub formatting: Option<DocumentFormattingCapabilities>,
    pub range_formatting: Option<DocumentRangeFormattingCapabilities>,
    pub on_type_formatting: Option<DocumentOnTypeFormattingCapabilities>,
    pub rename: Option<RenameCapabilities>,
    pub folding_range: Option<FoldingRangeCapabilities>,
    pub selection_range: Option<SelectionRangeCapabilities>,
    pub publish_diagnostics: Option<PublishDiagnosticsCapabilities>,
    pub call_hierarchy: Option<CallHierarchyCapabilities>,
    pub semantic_tokens: Option<SemanticTokensClientCapabilities>,
    pub linked_editing_range: Option<LinkedEditingRangeCapabilities>,
    pub moniker: Option<MonikerCapabilities>,
    pub type_hierarchy: Option<TypeHierarchyCapabilities>,
    pub inline_value: Option<InlineValueCapabilities>,
    pub inlay_hint: Option<InlayHintCapabilities>,
    pub diagnostic: Option<DiagnosticCapabilities>,
    pub inline_completion: Option<InlineCompletionCapabilities>,
}

/// 文本文档同步能力
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextDocumentSyncCapabilities {
    pub did_save: Option<bool>,
    pub will_save: Option<bool>,
    pub will_save_wait_until: Option<bool>,
    pub change: Option<u32>,
}

/// 窗口客户端能力
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WindowClientCapabilities {
    pub show_document: Option<ShowDocumentCapabilities>,
    pub work_done_progress: Option<bool>,
}

/// 显示文档能力
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShowDocumentCapabilities {
    pub support: bool,
}

/// 通用客户端能力
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeneralClientCapabilities {
    pub stale_request_support: Option<StaleRequestSupport>,
    pub regular_expressions: Option<RegularExpressions>,
    pub markdown: Option<Markdown>,
    pub position_encodings: Option<Vec<String>>,
}

/// 过期请求支持
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StaleRequestSupport {
    pub support: bool,
    pub cancel: bool,
    pub retry_on_content_modified: Vec<String>,
}

/// 正则表达式
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegularExpressions {
    pub engine: String,
    pub version: Option<String>,
}

/// Markdown
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Markdown {
    pub parser: String,
    pub version: Option<String>,
    pub allowed_tags: Option<Vec<String>>,
}

/// 工作区文件夹
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkspaceFolder {
    pub uri: String,
    pub name: String,
}

/// 初始化结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InitializeResult {
    pub capabilities: ServerCapabilities,
    pub server_info: Option<ServerInfo>,
}

/// 服务器能力
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServerCapabilities {
    pub text_document_sync: Option<TextDocumentSyncOptions>,
    pub hover_provider: Option<bool>,
    pub completion_provider: Option<CompletionOptions>,
    pub signature_help_provider: Option<SignatureHelpOptions>,
    pub declaration_provider: Option<bool>,
    pub definition_provider: Option<bool>,
    pub type_definition_provider: Option<bool>,
    pub implementation_provider: Option<bool>,
    pub references_provider: Option<bool>,
    pub document_highlight_provider: Option<bool>,
    pub document_symbol_provider: Option<bool>,
    pub code_action_provider: Option<bool>,
    pub code_lens_provider: Option<CodeLensOptions>,
    pub document_link_provider: Option<bool>,
    pub color_provider: Option<bool>,
    pub document_formatting_provider: Option<bool>,
    pub document_range_formatting_provider: Option<bool>,
    pub document_on_type_formatting_provider: Option<bool>,
    pub rename_provider: Option<bool>,
    pub folding_range_provider: Option<bool>,
    pub selection_range_provider: Option<bool>,
    pub execute_command_provider: Option<ExecuteCommandOptions>,
    pub workspace: Option<WorkspaceServerCapabilities>,
    pub semantic_tokens_provider: Option<SemanticTokensOptions>,
    pub call_hierarchy_provider: Option<bool>,
    pub linked_editing_range_provider: Option<bool>,
    pub moniker_provider: Option<bool>,
    pub type_hierarchy_provider: Option<bool>,
    pub inline_value_provider: Option<bool>,
    pub inlay_hint_provider: Option<bool>,
    pub diagnostic_provider: Option<bool>,
    pub inline_completion_provider: Option<bool>,
}

/// 文本文档同步选项
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextDocumentSyncOptions {
    pub open_close: Option<bool>,
    pub change: Option<u32>,
    pub will_save: Option<bool>,
    pub will_save_wait_until: Option<bool>,
    pub save: Option<bool>,
}

/// 服务器信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServerInfo {
    pub name: String,
    pub version: Option<String>,
}

/// 工作区服务器能力
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkspaceServerCapabilities {
    pub workspace_folders: Option<WorkspaceFoldersServerCapabilities>,
    pub file_operations: Option<FileOperationsServerCapabilities>,
}

/// 工作区文件夹服务器能力
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkspaceFoldersServerCapabilities {
    pub supported: bool,
    pub change_notifications: Option<bool>,
}

/// 文件操作服务器能力
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileOperationsServerCapabilities {
    pub did_create: Option<FileOperationRegistrationOptions>,
    pub will_create: Option<FileOperationRegistrationOptions>,
    pub did_rename: Option<FileOperationRegistrationOptions>,
    pub will_rename: Option<FileOperationRegistrationOptions>,
    pub did_delete: Option<FileOperationRegistrationOptions>,
    pub will_delete: Option<FileOperationRegistrationOptions>,
}

/// 文件操作注册选项
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileOperationRegistrationOptions {
    pub filters: Vec<FileOperationFilter>,
}

/// 文件操作过滤器
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileOperationFilter {
    pub scheme: Option<String>,
    pub pattern: FileOperationPattern,
}

/// 文件操作模式
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileOperationPattern {
    pub glob: String,
    pub matches: Option<String>,
    pub options: Option<FileOperationPatternOptions>,
}

/// 文件操作模式选项
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileOperationPatternOptions {
    pub ignore_case: Option<bool>,
}

/// 完成选项
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompletionOptions {
    pub resolve_provider: Option<bool>,
    pub trigger_characters: Option<Vec<String>>,
    pub all_commit_characters: Option<Vec<String>>,
    pub work_done_progress_options: WorkDoneProgressOptions,
}

/// 工作完成进度选项
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkDoneProgressOptions {
    pub work_done_progress: Option<bool>,
}

/// 签名帮助选项
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignatureHelpOptions {
    pub trigger_characters: Option<Vec<String>>,
    pub retrigger_characters: Option<Vec<String>>,
    pub work_done_progress_options: WorkDoneProgressOptions,
}

/// 代码 Lens 选项
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CodeLensOptions {
    pub resolve_provider: Option<bool>,
}

/// 执行命令选项
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecuteCommandOptions {
    pub commands: Vec<String>,
    pub work_done_progress_options: WorkDoneProgressOptions,
}

/// 语义 Token 选项
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SemanticTokensOptions {
    pub legend: SemanticTokensLegend,
    pub range: Option<bool>,
    pub full: Option<bool>,
    pub work_done_progress_options: WorkDoneProgressOptions,
}

/// 语义 Token 图例
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SemanticTokensLegend {
    pub token_types: Vec<String>,
    pub token_modifiers: Vec<String>,
}

/// 诊断
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Diagnostic {
    pub range: Range,
    pub severity: Option<u32>,
    pub code: Option<DiagnosticCode>,
    pub code_description: Option<CodeDescription>,
    pub source: Option<String>,
    pub message: String,
    pub tags: Option<Vec<u32>>,
    pub related_information: Option<Vec<DiagnosticRelatedInformation>>,
    pub data: Option<serde_json::Value>,
}

/// 诊断代码
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiagnosticCode {
    pub value: String,
    pub target: Option<String>,
}

/// 代码描述
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CodeDescription {
    pub href: String,
}

/// 诊断相关信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiagnosticRelatedInformation {
    pub location: Location,
    pub message: String,
}

/// 位置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Location {
    pub uri: String,
    pub range: Range,
}

/// 文本编辑
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextEdit {
    pub range: Range,
    pub new_text: String,
}

/// 工作区编辑
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkspaceEdit {
    pub changes: Option<HashMap<String, Vec<TextEdit>>>,
    pub document_changes: Option<Vec<TextDocumentEdit>>,
    pub change_annotations: Option<HashMap<u32, ChangeAnnotation>>,
}

/// 文本文档编辑
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextDocumentEdit {
    pub text_document: VersionedTextDocumentIdentifier,
    pub edits: Vec<TextEdit>,
}

/// 更改注释
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChangeAnnotation {
    pub label: String,
    pub needs_confirmation: Option<bool>,
    pub description: Option<String>,
}

/// 完成项目
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompletionItem {
    pub label: String,
    pub label_details: Option<CompletionItemLabelDetails>,
    pub kind: Option<u32>,
    pub tags: Option<Vec<u32>>,
    pub detail: Option<String>,
    pub documentation: Option<Documentation>,
    pub deprecated: Option<bool>,
    pub preselect: Option<bool>,
    pub sort_text: Option<String>,
    pub filter_text: Option<String>,
    pub insert_text: Option<String>,
    pub insert_text_format: Option<u32>,
    pub insert_text_mode: Option<u32>,
    pub text_edit: Option<TextEdit>,
    pub additional_text_edits: Option<Vec<TextEdit>>,
    pub commit_characters: Option<Vec<String>>,
    pub command: Option<Command>,
    pub data: Option<serde_json::Value>,
}

/// 完成项目标签详情
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompletionItemLabelDetails {
    pub detail: Option<String>,
    pub description: Option<String>,
}

/// 文档
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Documentation {
    pub kind: Option<String>,
    pub value: String,
}

/// 命令
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Command {
    pub title: String,
    pub command: String,
    pub arguments: Option<Vec<serde_json::Value>>,
}

/// LSP 请求
#[derive(Debug, Clone, Serialize)]
pub struct Request {
    pub jsonrpc: String,
    pub id: u64,
    pub method: String,
    pub params: Option<serde_json::Value>,
}

/// LSP 响应
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Response {
    pub jsonrpc: String,
    pub id: u64,
    pub result: Option<serde_json::Value>,
    pub error: Option<ResponseError>,
}

/// 响应错误
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResponseError {
    pub code: i32,
    pub message: String,
    pub data: Option<serde_json::Value>,
}

/// LSP 通知
#[derive(Debug, Clone, Serialize)]
pub struct Notification {
    pub jsonrpc: String,
    pub method: String,
    pub params: Option<serde_json::Value>,
}
