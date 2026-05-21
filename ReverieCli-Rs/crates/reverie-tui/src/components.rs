//! TUI 组件
//!
//! 提供各种 UI 组件：消息显示、输入框、工具调用面板等

use ratatui::{
    buffer::Buffer,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem, Paragraph, Widget},
};

use crate::state::{Message, MessageRole, Settings, Theme};

/// 消息显示组件
pub struct MessageDisplay<'a> {
    messages: &'a [&'a Message],
    theme: &'a Theme,
    settings: &'a Settings,
    scroll_offset: usize,
    max_height: u16,
}

impl<'a> MessageDisplay<'a> {
    pub fn new(
        messages: &'a [&'a Message],
        theme: &'a Theme,
        settings: &'a Settings,
        scroll_offset: usize,
        max_height: u16,
    ) -> Self {
        Self {
            messages,
            theme,
            settings,
            scroll_offset,
            max_height,
        }
    }
}

impl<'a> Widget for MessageDisplay<'a> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let visible_messages = if self.scroll_offset < self.messages.len() {
            &self.messages[self.scroll_offset..]
        } else {
            &self.messages[0..]
        };

        let mut y = area.top();
        for message in visible_messages.iter().take(self.max_height as usize) {
            if y >= area.bottom() {
                break;
            }

            let role_style = self.get_role_style(message.role);
            let prefix = self.get_role_prefix(message.role);

            let line = Line::from(vec![
                Span::styled(prefix, role_style),
                Span::styled(&message.content, Style::default().fg(Color::White)),
            ]);

            // 简单渲染（实际应该使用更复杂的布局）
            for (i, line_text) in line.spans.iter().enumerate() {
                let x = area.left() + (i as u16) * 2;
                if x < area.right() {
                    buf.set_string(x, y, &line_text.content, role_style);
                }
            }
            y += 1;
        }
    }
}

impl<'a> MessageDisplay<'a> {
    fn get_role_style(&self, role: MessageRole) -> Style {
        let color = match role {
            MessageRole::User => Color::Blue,
            MessageRole::Assistant => Color::Green,
            MessageRole::System => Color::Gray,
            MessageRole::Tool => Color::Magenta,
        };
        Style::default().fg(color)
    }

    fn get_role_prefix(&self, role: MessageRole) -> String {
        match role {
            MessageRole::User => "👤 ".to_string(),
            MessageRole::Assistant => "🤖 ".to_string(),
            MessageRole::System => "⚙️ ".to_string(),
            MessageRole::Tool => "🔧 ".to_string(),
        }
    }
}

/// 输入框组件
pub struct InputBox<'a> {
    input: &'a str,
    cursor: usize,
    prompt: &'a str,
    theme: &'a Theme,
}

impl<'a> InputBox<'a> {
    pub fn new(input: &'a str, cursor: usize, prompt: &'a str, theme: &'a Theme) -> Self {
        Self {
            input,
            cursor,
            prompt,
            theme,
        }
    }
}

impl<'a> Widget for InputBox<'a> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Cyan));

        block.render(area, buf);

        // 渲染提示
        let prompt_style = Style::default().fg(Color::Yellow);
        buf.set_string(area.left() + 1, area.top() + 1, self.prompt, prompt_style);

        // 渲染输入内容
        let input_style = Style::default().fg(Color::White);
        buf.set_string(
            area.left() + 1 + self.prompt.len() as u16,
            area.top() + 1,
            self.input,
            input_style,
        );

        // 渲染光标
        let cursor_x = area.left() + 1 + self.prompt.len() as u16 + self.cursor as u16;
        let _ = cursor_x;
    }
}

/// 工具调用面板
pub struct ToolCallPanel<'a> {
    tool_name: &'a str,
    tool_args: &'a serde_json::Value,
    tool_result: Option<&'a Result<String, String>>,
    theme: &'a Theme,
}

impl<'a> ToolCallPanel<'a> {
    pub fn new(
        tool_name: &'a str,
        tool_args: &'a serde_json::Value,
        tool_result: Option<&'a Result<String, String>>,
        theme: &'a Theme,
    ) -> Self {
        Self {
            tool_name,
            tool_args,
            tool_result,
            theme,
        }
    }
}

impl<'a> Widget for ToolCallPanel<'a> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let block = Block::default()
            .title(format!("🔧 {}", self.tool_name))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Magenta));

        block.render(area, buf);

        let mut y = area.top() + 1;

        // 渲染工具参数
        if let Some(args) = self.tool_args.as_object() {
            for (key, value) in args.iter().take(5) {
                if y >= area.bottom() {
                    break;
                }
                let line = format!("  {} = {}", key, value);
                buf.set_string(area.left() + 1, y, &line, Style::default().fg(Color::Cyan));
                y += 1;
            }
        }

        // 渲染工具结果
        if let Some(result) = self.tool_result {
            if y >= area.bottom() {
                return;
            }
            let (status, content) = match result {
                Ok(content) => ("✅", content.as_str()),
                Err(content) => ("❌", content.as_str()),
            };
            let style = if result.is_ok() {
                Style::default().fg(Color::Green)
            } else {
                Style::default().fg(Color::Red)
            };
            buf.set_string(
                area.left() + 1,
                y,
                &format!("{} {}", status, content),
                style,
            );
        }
    }
}

/// 会话列表组件
pub struct SessionList<'a> {
    sessions: &'a [crate::state::Session],
    selected: Option<usize>,
    theme: &'a Theme,
}

impl<'a> SessionList<'a> {
    pub fn new(
        sessions: &'a [crate::state::Session],
        selected: Option<usize>,
        theme: &'a Theme,
    ) -> Self {
        Self {
            sessions,
            selected,
            theme,
        }
    }
}

impl<'a> Widget for SessionList<'a> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let items: Vec<ListItem> = self
            .sessions
            .iter()
            .enumerate()
            .map(|(i, session)| {
                let style = if Some(i) == self.selected {
                    Style::default()
                        .fg(Color::Yellow)
                        .add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(Color::White)
                };
                ListItem::new(Line::from(session.title.clone())).style(style)
            })
            .collect();

        let list = List::new(items).block(Block::default().title("📁 会话").borders(Borders::ALL));

        list.render(area, buf);
    }
}

/// 帮助面板
pub struct HelpPanel {
    theme: Theme,
}

impl HelpPanel {
    pub fn new(theme: Theme) -> Self {
        Self { theme }
    }
}

impl Widget for HelpPanel {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let block = Block::default()
            .title("❓ 帮助")
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Yellow));

        block.render(area, buf);

        let help_lines = vec![
            "Ctrl+Q  退出",
            "F1      帮助",
            "F2      设置",
            "F3      历史",
            "Enter   发送消息",
            "Ctrl+C  停止生成",
            "Ctrl+R  重新生成",
            "Ctrl+F  搜索",
            "Ctrl+S  保存会话",
            "Ctrl+L  加载会话",
            "Ctrl+D  删除会话",
            "Ctrl+M  切换模式",
            "Ctrl+L  清除屏幕",
            "↑↓      上下移动",
            "Home    滚动到顶部",
            "End     滚动到底部",
        ];

        let mut y = area.top() + 1;
        for line in help_lines {
            if y >= area.bottom() {
                break;
            }
            buf.set_string(area.left() + 1, y, line, Style::default().fg(Color::White));
            y += 1;
        }
    }
}

/// 状态行组件
pub struct StatusBar<'a> {
    mode: &'a str,
    session_title: Option<&'a str>,
    is_generating: bool,
    message_count: usize,
    theme: &'a Theme,
}

impl<'a> StatusBar<'a> {
    pub fn new(
        mode: &'a str,
        session_title: Option<&'a str>,
        is_generating: bool,
        message_count: usize,
        theme: &'a Theme,
    ) -> Self {
        Self {
            mode,
            session_title,
            is_generating,
            message_count,
            theme,
        }
    }
}

impl<'a> Widget for StatusBar<'a> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let status_text = format!(
            "Mode: {} | {} | Messages: {} | {}",
            self.mode,
            self.session_title.unwrap_or("No session"),
            self.message_count,
            if self.is_generating {
                "⏳ Generating..."
            } else {
                "Ready"
            }
        );

        let style = Style::default().fg(Color::White).bg(Color::DarkGray);

        let paragraph = Paragraph::new(status_text)
            .style(style)
            .alignment(ratatui::layout::Alignment::Center);

        paragraph.render(area, buf);
    }
}

/// 布局组件
#[derive(Clone, Copy)]
pub struct MainLayout {
    /// 消息区域高度比例
    pub message_ratio: u16,
    /// 输入区域高度
    pub input_height: u16,
    /// 侧边栏宽度比例
    pub sidebar_ratio: u16,
}

impl MainLayout {
    pub fn new() -> Self {
        Self {
            message_ratio: 70,
            input_height: 3,
            sidebar_ratio: 20,
        }
    }

    /// 创建主布局
    pub fn split(&self, area: Rect) -> (Rect, Rect, Rect) {
        // 主区域（消息 + 输入）
        let main_area = {
            let chunks = Layout::default()
                .direction(Direction::Vertical)
                .constraints([
                    Constraint::Percentage(self.message_ratio),
                    Constraint::Length(self.input_height),
                ])
                .split(area);
            (chunks[0], chunks[1])
        };

        // 如果有侧边栏
        let sidebar_area = if self.sidebar_ratio > 0 {
            let chunks = Layout::default()
                .direction(Direction::Horizontal)
                .constraints([
                    Constraint::Percentage(self.sidebar_ratio),
                    Constraint::Percentage(100 - self.sidebar_ratio),
                ])
                .split(area);
            Some(chunks[0])
        } else {
            None
        };

        (main_area.0, main_area.1, sidebar_area.unwrap_or(area))
    }
}

impl Default for MainLayout {
    fn default() -> Self {
        Self::new()
    }
}
