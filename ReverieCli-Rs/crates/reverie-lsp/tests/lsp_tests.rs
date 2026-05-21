//! LSP 测试

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::*;
    
    #[test]
    fn test_position_serialization() {
        let pos = Position {
            line: 10,
            character: 5,
        };
        
        let serialized = serde_json::to_string(&pos).unwrap();
        let deserialized: Position = serde_json::from_str(&serialized).unwrap();
        
        assert_eq!(pos.line, deserialized.line);
        assert_eq!(pos.character, deserialized.character);
    }
    
    #[test]
    fn test_range_serialization() {
        let range = Range {
            start: Position { line: 0, character: 0 },
            end: Position { line: 1, character: 10 },
        };
        
        let serialized = serde_json::to_string(&range).unwrap();
        let deserialized: Range = serde_json::from_str(&serialized).unwrap();
        
        assert_eq!(range.start.line, deserialized.start.line);
        assert_eq!(range.end.character, deserialized.end.character);
    }
    
    #[test]
    fn test_request_serialization() {
        let request = Request {
            jsonrpc: "2.0".to_string(),
            id: 1,
            method: "initialize".to_string(),
            params: None,
        };
        
        let serialized = serde_json::to_string(&request).unwrap();
        assert!(serialized.contains("\"jsonrpc\":\"2.0\""));
        assert!(serialized.contains("\"method\":\"initialize\""));
    }
    
    #[test]
    fn test_response_serialization() {
        let response = Response {
            jsonrpc: "2.0".to_string(),
            id: 1,
            result: Some(serde_json::json!({"capabilities": {}})),
            error: None,
        };
        
        let serialized = serde_json::to_string(&response).unwrap();
        assert!(serialized.contains("\"result\""));
        assert!(!serialized.contains("\"error\""));
    }
    
    #[test]
    fn test_error_response_serialization() {
        let response = Response {
            jsonrpc: "2.0".to_string(),
            id: 1,
            result: None,
            error: Some(ResponseError {
                code: -32600,
                message: "Invalid Request".to_string(),
                data: None,
            }),
        };
        
        let serialized = serde_json::to_string(&response).unwrap();
        assert!(serialized.contains("\"error\""));
        assert!(serialized.contains("-32600"));
    }
    
    #[test]
    fn test_notification_serialization() {
        let notification = Notification {
            jsonrpc: "2.0".to_string(),
            method: "textDocument/didOpen".to_string(),
            params: None,
        };
        
        let serialized = serde_json::to_string(&notification).unwrap();
        assert!(serialized.contains("\"method\":\"textDocument/didOpen\""));
        assert!(!serialized.contains("\"id\""));
    }
    
    #[test]
    fn test_completion_item_serialization() {
        let item = CompletionItem {
            label: "println!".to_string(),
            label_details: None,
            kind: Some(3),
            tags: None,
            detail: Some("macro".to_string()),
            documentation: None,
            deprecated: None,
            preselect: None,
            sort_text: None,
            filter_text: None,
            insert_text: None,
            insert_text_format: None,
            insert_text_mode: None,
            text_edit: None,
            additional_text_edits: None,
            commit_characters: None,
            command: None,
            data: None,
        };
        
        let serialized = serde_json::to_string(&item).unwrap();
        assert!(serialized.contains("\"label\":\"println!\""));
    }
    
    #[test]
    fn test_diagnostic_serialization() {
        let diagnostic = Diagnostic {
            range: Range {
                start: Position { line: 0, character: 0 },
                end: Position { line: 0, character: 5 },
            },
            severity: Some(1),
            code: None,
            code_description: None,
            source: Some("rustc".to_string()),
            message: "unused variable".to_string(),
            tags: None,
            related_information: None,
            data: None,
        };
        
        let serialized = serde_json::to_string(&diagnostic).unwrap();
        assert!(serialized.contains("\"message\":\"unused variable\""));
    }
    
    #[test]
    fn test_workspace_edit_serialization() {
        let edit = WorkspaceEdit {
            changes: Some({
                let mut map = std::collections::HashMap::new();
                map.insert(
                    "file:///test.rs".to_string(),
                    vec![TextEdit {
                        range: Range {
                            start: Position { line: 0, character: 0 },
                            end: Position { line: 0, character: 0 },
                        },
                        new_text: "fn main() {}".to_string(),
                    }],
                );
                map
            }),
            document_changes: None,
            change_annotations: None,
        };
        
        let serialized = serde_json::to_string(&edit).unwrap();
        assert!(serialized.contains("\"changes\""));
    }
    
    #[test]
    fn test_initialize_params_serialization() {
        let params = InitializeParams {
            process_id: Some(12345),
            root_uri: Some("file:///project".to_string()),
            root_path: None,
            initialization_options: None,
            capabilities: ClientCapabilities {
                workspace: None,
                text_document: None,
                window: None,
                general: None,
            },
            trace: None,
            workspace_folders: None,
        };
        
        let serialized = serde_json::to_string(&params).unwrap();
        assert!(serialized.contains("\"processId\":12345"));
        assert!(serialized.contains("\"rootUri\":\"file:///project\""));
    }
}
