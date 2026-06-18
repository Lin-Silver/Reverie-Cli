//! TUI 状态管理
//!
//! 管理应用状态、消息历史、会话等

use serde::{Deserialize, Serialize};
use std::collections::VecDeque;

/// 消息角色
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MessageRole {
    User,
    Assistant,
    System,
    Tool,
}

/// 消息内容
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub role: MessageRole,
    pub content: String,
    pub timestamp: u64,
    pub tool_call_id: Option<String>,
    pub tool_name: Option<String>,
    pub tool_args: Option<serde_json::Value>,
    pub tool_result: Option<Result<String, String>>,
}

impl Message {
    pub fn new(role: MessageRole, content: String) -> Self {
        Self {
            role,
            content,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64,
            tool_call_id: None,
            tool_name: None,
            tool_args: None,
            tool_result: None,
        }
    }

    pub fn with_tool_call(
        role: MessageRole,
        content: String,
        tool_call_id: String,
        tool_name: String,
        tool_args: serde_json::Value,
    ) -> Self {
        Self {
            role,
            content,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64,
            tool_call_id: Some(tool_call_id),
            tool_name: Some(tool_name),
            tool_args: Some(tool_args),
            tool_result: None,
        }
    }

    pub fn with_tool_result(
        role: MessageRole,
        content: String,
        tool_call_id: String,
        result: Result<String, String>,
    ) -> Self {
        Self {
            role,
            content,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64,
            tool_call_id: Some(tool_call_id),
            tool_name: None,
            tool_args: None,
            tool_result: Some(result),
        }
    }
}

/// 会话信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Session {
    pub id: String,
    pub title: String,
    pub messages: Vec<Message>,
    pub mode: String,
    pub created_at: u64,
    pub updated_at: u64,
}

impl Session {
    pub fn new(id: String, title: String, mode: String) -> Self {
        Self {
            id,
            title,
            messages: Vec::new(),
            mode,
            created_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64,
            updated_at: 0,
        }
    }

    pub fn add_message(&mut self, message: Message) {
        self.messages.push(message);
        self.updated_at = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;
    }

    pub fn clear(&mut self) {
        self.messages.clear();
    }
}

/// 应用状态
#[derive(Debug, Clone)]
pub struct AppState {
    /// 当前会话
    pub current_session: Option<Session>,
    /// 所有会话
    pub sessions: Vec<Session>,
    /// 消息历史（用于快速访问）
    pub message_history: VecDeque<Message>,
    /// 当前输入
    pub input: String,
    /// 输入光标位置
    pub input_cursor: usize,
    /// 是否正在生成
    pub is_generating: bool,
    /// 当前模式
    pub mode: String,
    /// 当前主题
    pub theme: Theme,
    /// 显示设置
    pub settings: Settings,
    /// 滚动偏移
    pub scroll_offset: usize,
    /// 搜索模式
    pub is_searching: bool,
    /// 搜索查询
    pub search_query: String,
    /// 搜索结果索引
    pub search_index: usize,
    /// 显示的帮助
    pub show_help: bool,
    /// 显示的设置面板
    pub show_settings: bool,
    /// 显示的历史面板
    pub show_history: bool,
    /// 选中的工具结果
    pub selected_tool_result: Option<String>,
    /// 工具调用历史
    pub tool_call_history: Vec<(String, serde_json::Value)>,
}

/// 主题设置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Theme {
    /// 主色
    pub primary: String,
    /// 次色
    pub secondary: String,
    /// 背景色
    pub background: String,
    /// 前景色
    pub foreground: String,
    /// 高亮色
    pub highlight: String,
    /// 错误色
    pub error: String,
    /// 警告色
    pub warning: String,
    /// 成功色
    pub success: String,
    /// 用户消息颜色
    pub user_message: String,
    /// 助手消息颜色
    pub assistant_message: String,
    /// 系统消息颜色
    pub system_message: String,
    /// 工具调用颜色
    pub tool_call: String,
    /// 工具结果颜色
    pub tool_result: String,
}

impl Default for Theme {
    fn default() -> Self {
        Self {
            primary: "cyan".to_string(),
            secondary: "blue".to_string(),
            background: "black".to_string(),
            foreground: "white".to_string(),
            highlight: "yellow".to_string(),
            error: "red".to_string(),
            warning: "yellow".to_string(),
            success: "green".to_string(),
            user_message: "blue".to_string(),
            assistant_message: "green".to_string(),
            system_message: "gray".to_string(),
            tool_call: "magenta".to_string(),
            tool_result: "cyan".to_string(),
        }
    }
}

/// 设置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Settings {
    /// 是否显示状态行
    pub show_status_line: bool,
    /// 是否显示时间戳
    pub show_timestamp: bool,
    /// 是否显示工具调用详情
    pub show_tool_details: bool,
    /// 是否自动滚动到底部
    pub auto_scroll: bool,
    /// 消息最大显示行数
    pub max_message_lines: usize,
    /// 输入提示
    pub prompt_prefix: String,
    /// 主题名称
    pub theme_name: String,
    /// 字体大小
    pub font_size: u16,
    /// 是否启用语法高亮
    pub syntax_highlight: bool,
    /// 是否启用鼠标
    pub enable_mouse: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            show_status_line: true,
            show_timestamp: true,
            show_tool_details: true,
            auto_scroll: true,
            max_message_lines: 100,
            prompt_prefix: "▶ ".to_string(),
            theme_name: "default".to_string(),
            font_size: 1,
            syntax_highlight: true,
            enable_mouse: true,
        }
    }
}

impl AppState {
    /// 创建新的应用状态
    pub fn new(mode: String) -> Self {
        Self {
            current_session: None,
            sessions: Vec::new(),
            message_history: VecDeque::new(),
            input: String::new(),
            input_cursor: 0,
            is_generating: false,
            mode,
            theme: Theme::default(),
            settings: Settings::default(),
            scroll_offset: 0,
            is_searching: false,
            search_query: String::new(),
            search_index: 0,
            show_help: false,
            show_settings: false,
            show_history: false,
            selected_tool_result: None,
            tool_call_history: Vec::new(),
        }
    }

    /// 创建新会话
    pub fn create_session(&mut self, title: String) -> String {
        let id = format!(
            "session-{}-{}",
            chrono::Utc::now().timestamp_millis(),
            self.sessions.len()
        );
        let session = Session::new(id.clone(), title, self.mode.clone());
        self.sessions.push(session);
        self.current_session = self.sessions.last_mut().cloned();
        id
    }

    /// 切换会话
    pub fn switch_session(&mut self, session_id: &str) {
        if let Some(session) = self.sessions.iter().find(|s| s.id == session_id) {
            self.current_session = Some(session.clone());
        }
    }

    /// 添加消息到当前会话
    pub fn add_message(&mut self, message: Message) {
        if let Some(session) = self.current_session.as_mut() {
            session.add_message(message.clone());
        }
        self.message_history.push_back(message);

        // 限制历史长度
        if self.message_history.len() > 1000 {
            self.message_history.pop_front();
        }

        // 自动滚动
        if self.settings.auto_scroll {
            self.scroll_offset = usize::MAX;
        }
    }

    /// 清除当前会话
    pub fn clear_current_session(&mut self) {
        if let Some(session) = self.current_session.as_mut() {
            session.clear();
        }
    }

    /// 删除会话
    pub fn delete_session(&mut self, session_id: &str) {
        self.sessions.retain(|s| s.id != session_id);
        if self
            .current_session
            .as_ref()
            .map(|s| s.id == session_id)
            .unwrap_or(false)
        {
            self.current_session = self.sessions.first().cloned();
        }
    }

    /// 获取当前消息
    pub fn current_messages(&self) -> Vec<&Message> {
        self.current_session
            .as_ref()
            .map(|s| s.messages.iter().collect())
            .unwrap_or_default()
    }

    /// 切换搜索模式
    pub fn toggle_search(&mut self) {
        self.is_searching = !self.is_searching;
        if !self.is_searching {
            self.search_query.clear();
            self.search_index = 0;
        }
    }

    /// 更新输入
    pub fn update_input(&mut self, input: String) {
        self.input = input;
        self.input_cursor = self.input.len();
    }

    /// 在光标位置插入字符
    pub fn insert_char(&mut self, c: char) {
        self.input.insert(self.input_cursor, c);
        self.input_cursor += c.len_utf8();
    }

    /// 删除光标前的字符
    pub fn delete_backward(&mut self) {
        if self.input_cursor > 0 {
            if let Some((pos, _)) = self.input[..self.input_cursor].char_indices().last() {
                self.input.drain(pos..self.input_cursor);
                self.input_cursor = pos;
            }
        }
    }

    /// 删除光标后的字符
    pub fn delete_forward(&mut self) {
        if self.input_cursor < self.input.len() {
            // 找到下一个字符的起始位置
            let next = next_char_boundary(&self.input, self.input_cursor);
            self.input.drain(self.input_cursor..next);
        }
    }

    /// 移动光标
    pub fn move_cursor(&mut self, direction: Direction) {
        match direction {
            Direction::Left => {
                if self.input_cursor > 0 {
                    // 找到前一个字符的起始位置
                    self.input_cursor = prev_char_boundary(&self.input, self.input_cursor);
                }
            }
            Direction::Right => {
                if self.input_cursor < self.input.len() {
                    // 找到下一个字符的起始位置
                    self.input_cursor = next_char_boundary(&self.input, self.input_cursor);
                }
            }
            Direction::Home => {
                self.input_cursor = 0;
            }
            Direction::End => {
                self.input_cursor = self.input.len();
            }
        }
    }
}

/// 光标方向
#[derive(Debug, Clone, Copy)]
pub enum Direction {
    Left,
    Right,
    Home,
    End,
}

fn prev_char_boundary(input: &str, cursor: usize) -> usize {
    input[..cursor.min(input.len())]
        .char_indices()
        .last()
        .map(|(index, _)| index)
        .unwrap_or(0)
}

fn next_char_boundary(input: &str, cursor: usize) -> usize {
    if cursor >= input.len() {
        return input.len();
    }
    input[cursor..]
        .char_indices()
        .nth(1)
        .map(|(offset, _)| cursor + offset)
        .unwrap_or(input.len())
}
