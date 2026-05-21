//! TUI 事件处理器
//! 
//! 处理键盘输入、鼠标事件和应用程序逻辑

use crossterm::event::{KeyCode, KeyModifiers};
use std::sync::mpsc::{Receiver, Sender};

use crate::event::{Event, keys};
use crate::state::{AppState, Direction, Message, MessageRole};

/// 事件处理器
pub struct EventHandler {
    /// 事件通道发送器
    tx: Sender<Event>,
    /// 事件通道接收器
    rx: Receiver<Event>,
    /// 应用状态
    app_state: AppState,
    /// 是否退出
    should_quit: bool,
}

impl EventHandler {
    /// 创建新的事件处理器
    pub fn new(app_state: AppState) -> Self {
        let (tx, rx) = std::sync::mpsc::channel();
        
        Self {
            tx,
            rx,
            app_state,
            should_quit: false,
        }
    }
    
    /// 获取应用状态引用
    pub fn app_state(&self) -> &AppState {
        &self.app_state
    }
    
    /// 获取应用状态可变引用
    pub fn app_state_mut(&mut self) -> &mut AppState {
        &mut self.app_state
    }
    
    /// 获取下一个事件
    pub fn next(&self) -> Result<Event, Box<dyn std::error::Error>> {
        loop {
            if let Ok(event) = self.rx.try_recv() {
                return Ok(event);
            }
            
            if self.should_quit {
                return Ok(Event::Quit);
            }
            
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
    }
    
    /// 发送事件
    pub fn send(&self, event: Event) -> Result<(), Box<dyn std::error::Error>> {
        self.tx.send(event)?;
        Ok(())
    }
    
    /// 处理事件
    pub fn handle_event(&mut self, event: Event) {
        match event {
            Event::Key(key) => self.handle_key(key),
            Event::SendMessage(content) => self.handle_send_message(content),
            Event::SelectSession(session_id) => self.handle_select_session(&session_id),
            Event::SwitchMode(mode) => self.handle_switch_mode(&mode),
            Event::ToolCall { tool_name, args } => self.handle_tool_call(&tool_name, args),
            Event::ToolResult { tool_name, result } => self.handle_tool_result(&tool_name, result),
            Event::ShowHelp => self.app_state.show_help = true,
            Event::ShowSettings => self.app_state.show_settings = true,
            Event::ShowHistory => self.app_state.show_history = true,
            Event::ClearScreen => self.app_state.scroll_offset = 0,
            Event::CopyContent(content) => self.handle_copy(content),
            Event::SaveSession => self.handle_save_session(),
            Event::LoadSession => self.handle_load_session(),
            Event::DeleteSession(session_id) => self.handle_delete_session(&session_id),
            Event::Regenerate => self.handle_regenerate(),
            Event::StopGeneration => self.handle_stop_generation(),
            Event::ScrollToTop => self.app_state.scroll_offset = 0,
            Event::ScrollToBottom => self.app_state.scroll_offset = usize::MAX,
            Event::Search(query) => self.handle_search(query),
            Event::NextSearchResult => self.handle_next_search(),
            Event::PreviousSearchResult => self.handle_previous_search(),
            Event::CancelSearch => self.app_state.is_searching = false,
            Event::Quit => self.should_quit = true,
            Event::Refresh => {}
            Event::Resize(_, _) => {}
            Event::Mouse(_) => {}
            Event::Terminal(_) => {}
        }
    }
    
    /// 处理键盘事件
    fn handle_key(&mut self, key: crossterm::event::KeyEvent) {
        // 如果显示帮助或设置面板，只处理关闭事件
        if self.app_state.show_help || self.app_state.show_settings || self.app_state.show_history {
            if key.code == KeyCode::Esc || 
               (key.code == KeyCode::Char('q') && key.modifiers.contains(KeyModifiers::CONTROL)) {
                self.app_state.show_help = false;
                self.app_state.show_settings = false;
                self.app_state.show_history = false;
            }
            return;
        }
        
        // 如果正在搜索
        if self.app_state.is_searching {
            match key.code {
                KeyCode::Enter => {
                    self.app_state.is_searching = false;
                }
                KeyCode::Esc => {
                    self.app_state.is_searching = false;
                    self.app_state.search_query.clear();
                }
                KeyCode::Char(c) => {
                    self.app_state.search_query.push(c);
                }
                KeyCode::Backspace => {
                    self.app_state.search_query.pop();
                }
                KeyCode::Up => self.handle_previous_search(),
                KeyCode::Down => self.handle_next_search(),
                _ => {}
            }
            return;
        }
        
        // 在输入框中输入
        if key.code == KeyCode::Char('v') && key.modifiers.contains(KeyModifiers::CONTROL) {
            // Ctrl+V 粘贴（简化处理）
            return;
        }
        
        match key.code {
            KeyCode::Char('q') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.should_quit = true;
            }
            KeyCode::F(1) => self.app_state.show_help = true,
            KeyCode::F(2) => self.app_state.show_settings = true,
            KeyCode::F(3) => self.app_state.show_history = true,
            KeyCode::Enter => self.handle_send_message(self.app_state.input.clone()),
            KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.handle_stop_generation();
            }
            KeyCode::Char('r') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.handle_regenerate();
            }
            KeyCode::Char('f') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.app_state.is_searching = true;
                self.app_state.search_query.clear();
            }
            KeyCode::Char('s') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.handle_save_session();
            }
            KeyCode::Char('l') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.handle_load_session();
            }
            KeyCode::Char('d') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                if let Some(session) = &self.app_state.current_session {
                    self.handle_delete_session(&session.id);
                }
            }
            KeyCode::Char('m') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.handle_switch_mode("reverie-gamer");
            }
            KeyCode::Char('l') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.app_state.scroll_offset = 0;
            }
            KeyCode::Home | KeyCode::Char('g') => {
                self.app_state.scroll_offset = 0;
            }
            KeyCode::End | KeyCode::Char('G') => {
                self.app_state.scroll_offset = usize::MAX;
            }
            KeyCode::PageUp if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.handle_switch_session(-1);
            }
            KeyCode::PageDown if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.handle_switch_session(1);
            }
            KeyCode::Up | KeyCode::Char('k') => {
                self.app_state.move_cursor(Direction::Left);
            }
            KeyCode::Down | KeyCode::Char('j') => {
                self.app_state.move_cursor(Direction::Right);
            }
            KeyCode::Left | KeyCode::Char('h') => {
                self.app_state.move_cursor(Direction::Left);
            }
            KeyCode::Right | KeyCode::Char('l') => {
                self.app_state.move_cursor(Direction::Right);
            }
            KeyCode::Backspace => {
                self.app_state.delete_backward();
            }
            KeyCode::Delete => {
                self.app_state.delete_forward();
            }
            KeyCode::Char(c) => {
                self.app_state.insert_char(c);
            }
            _ => {}
        }
    }
    
    /// 处理发送消息
    fn handle_send_message(&mut self, content: String) {
        if content.trim().is_empty() {
            return;
        }
        
        // 创建用户消息
        let message = Message::new(MessageRole::User, content.clone());
        self.app_state.add_message(message);
        
        // 清空输入
        self.app_state.update_input(String::new());
    }
    
    /// 处理选择会话
    fn handle_select_session(&mut self, session_id: &str) {
        self.app_state.switch_session(session_id);
    }
    
    /// 处理切换模式
    fn handle_switch_mode(&mut self, mode: &str) {
        self.app_state.mode = mode.to_string();
    }
    
    /// 处理工具调用
    fn handle_tool_call(&mut self, tool_name: &str, args: serde_json::Value) {
        // 记录工具调用历史
        self.app_state.tool_call_history.push((tool_name.to_string(), args.clone()));
        
        // 创建工具调用消息
        let message = Message::with_tool_call(
            MessageRole::Assistant,
            format!("Calling tool: {}", tool_name),
            format!("call-{}", chrono::Utc::now().timestamp_millis()),
            tool_name.to_string(),
            args,
        );
        self.app_state.add_message(message);
    }
    
    /// 处理工具结果
    fn handle_tool_result(&mut self, tool_name: &str, result: Result<String, String>) {
        // 查找对应的工具调用
        if let Some((_, _)) = self.app_state.tool_call_history.last() {
            let message = Message::with_tool_result(
                MessageRole::Tool,
                format!("Tool result: {}", tool_name),
                format!("call-{}", chrono::Utc::now().timestamp_millis()),
                result,
            );
            self.app_state.add_message(message);
        }
    }
    
    /// 处理复制
    fn handle_copy(&self, content: String) {
        // 简化处理：实际应该使用剪贴板库
        eprintln!("Copied: {}", content);
    }
    
    /// 处理保存会话
    fn handle_save_session(&self) {
        // 简化处理：实际应该保存到文件
        eprintln!("Session saved");
    }
    
    /// 处理加载会话
    fn handle_load_session(&mut self) {
        // 简化处理：实际应该从文件加载
        eprintln!("Session loaded");
    }
    
    /// 处理删除会话
    fn handle_delete_session(&mut self, session_id: &str) {
        self.app_state.delete_session(session_id);
    }
    
    /// 处理重新生成
    fn handle_regenerate(&self) {
        // 简化处理：实际应该请求重新生成最后一条助手消息
        eprintln!("Regenerating...");
    }
    
    /// 处理停止生成
    fn handle_stop_generation(&mut self) {
        self.app_state.is_generating = false;
    }
    
    /// 处理搜索
    fn handle_search(&mut self, query: String) {
        self.app_state.search_query = query;
        self.app_state.search_index = 0;
    }
    
    /// 处理下一个搜索结果
    fn handle_next_search(&mut self) {
        self.app_state.search_index = self.app_state.search_index.saturating_add(1);
    }
    
    /// 处理上一个搜索结果
    fn handle_previous_search(&mut self) {
        self.app_state.search_index = self.app_state.search_index.saturating_sub(1);
    }
    
    /// 处理切换会话
    fn handle_switch_session(&mut self, delta: i32) {
        if self.app_state.sessions.is_empty() {
            return;
        }
        
        let current_index = self.app_state.sessions.iter().position(|s| {
            self.app_state.current_session.as_ref().map(|cs| cs.id == s.id).unwrap_or(false)
        }).unwrap_or(0);
        
        let new_index = ((current_index as i32) + delta).rem_euclid(self.app_state.sessions.len() as i32) as usize;
        self.app_state.switch_session(&self.app_state.sessions[new_index].id);
    }
    
    /// 检查是否应该退出
    pub fn should_quit(&self) -> bool {
        self.should_quit
    }
}
