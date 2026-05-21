//! TUI 测试

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::{AppState, Message, MessageRole};
    use crate::event::Event;
    
    #[test]
    fn test_app_state_creation() {
        let state = AppState::new("reverie".to_string());
        assert_eq!(state.mode, "reverie");
        assert!(!state.is_generating);
        assert!(state.sessions.is_empty());
    }
    
    #[test]
    fn test_message_creation() {
        let msg = Message::new(MessageRole::User, "Hello".to_string());
        assert_eq!(msg.role, MessageRole::User);
        assert_eq!(msg.content, "Hello");
        assert!(msg.timestamp > 0);
    }
    
    #[test]
    fn test_session_creation() {
        let mut state = AppState::new("reverie".to_string());
        let session_id = state.create_session("Test Session".to_string());
        
        assert_eq!(state.sessions.len(), 1);
        assert!(state.current_session.is_some());
        assert_eq!(state.current_session.as_ref().unwrap().title, "Test Session");
    }
    
    #[test]
    fn test_add_message() {
        let mut state = AppState::new("reverie".to_string());
        state.create_session("Test".to_string());
        
        let msg = Message::new(MessageRole::User, "Test".to_string());
        state.add_message(msg);
        
        assert_eq!(state.current_messages().len(), 1);
        assert_eq!(state.message_history.len(), 1);
    }
    
    #[test]
    fn test_input_editing() {
        let mut state = AppState::new("reverie".to_string());
        
        state.update_input("Hello".to_string());
        assert_eq!(state.input, "Hello");
        assert_eq!(state.input_cursor, 5);
        
        state.insert_char('!');
        assert_eq!(state.input, "Hello!");
        assert_eq!(state.input_cursor, 6);
        
        state.delete_backward();
        assert_eq!(state.input, "Hello");
        assert_eq!(state.input_cursor, 5);
    }
    
    #[test]
    fn test_cursor_movement() {
        let mut state = AppState::new("reverie".to_string());
        state.update_input("Hello World".to_string());
        
        state.move_cursor(crate::state::Direction::Left);
        assert_eq!(state.input_cursor, 10);
        
        state.move_cursor(crate::state::Direction::Left);
        assert_eq!(state.input_cursor, 9);
        
        state.move_cursor(crate::state::Direction::Home);
        assert_eq!(state.input_cursor, 0);
        
        state.move_cursor(crate::state::Direction::End);
        assert_eq!(state.input_cursor, 11);
    }
    
    #[test]
    fn test_search_mode() {
        let mut state = AppState::new("reverie".to_string());
        
        assert!(!state.is_searching);
        
        state.is_searching = true;
        state.search_query = "test".to_string();
        
        assert!(state.is_searching);
        assert_eq!(state.search_query, "test");
        
        state.is_searching = false;
        assert!(!state.is_searching);
    }
    
    #[test]
    fn test_session_deletion() {
        let mut state = AppState::new("reverie".to_string());
        let id1 = state.create_session("Session 1".to_string());
        let id2 = state.create_session("Session 2".to_string());
        
        assert_eq!(state.sessions.len(), 2);
        
        state.delete_session(&id1);
        assert_eq!(state.sessions.len(), 1);
    }
}
