//! TUI 渲染
//!
//! 负责将应用状态渲染到终端

use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::Line,
    widgets::{Block, Borders, Clear, List, ListItem, Paragraph},
    Frame, Terminal,
};

use crate::components::{HelpPanel, InputBox, MainLayout, MessageDisplay, SessionList, StatusBar};
use crate::state::{AppState, Message};

/// TUI 渲染器
pub struct TuiRenderer {
    /// 终端实例
    terminal: Terminal<ratatui::backend::CrosstermBackend<std::io::Stdout>>,
    /// 主布局
    layout: MainLayout,
}

impl TuiRenderer {
    /// 创建新的渲染器
    pub fn new() -> Result<Self, Box<dyn std::error::Error>> {
        let backend = ratatui::backend::CrosstermBackend::new(std::io::stdout());
        let terminal = Terminal::new(backend)?;

        Ok(Self {
            terminal,
            layout: MainLayout::new(),
        })
    }

    /// 渲染应用状态
    pub fn render(&mut self, app_state: &AppState) -> Result<(), Box<dyn std::error::Error>> {
        let layout = self.layout;
        self.terminal.draw(|frame| {
            let area = frame.area();

            // 如果显示帮助面板
            if app_state.show_help {
                Self::render_help_overlay(frame, area, &app_state.theme);
                return;
            }

            // 如果显示设置面板
            if app_state.show_settings {
                Self::render_settings_overlay(frame, area, &app_state.theme, &app_state.settings);
                return;
            }

            // 如果显示历史面板
            if app_state.show_history {
                Self::render_history_overlay(frame, area, &app_state.theme, &app_state.sessions);
                return;
            }

            // 主布局
            let (message_area, input_area, sidebar_area) = layout.split(area);

            // 渲染侧边栏（会话列表）
            if layout.sidebar_ratio > 0 {
                Self::render_sidebar(frame, sidebar_area, &app_state);
            }

            // 渲染消息区域
            Self::render_messages(frame, message_area, &app_state);

            // 渲染输入区域
            Self::render_input(frame, input_area, &app_state);

            // 渲染状态行
            if app_state.settings.show_status_line {
                Self::render_status_bar(frame, area, &app_state);
            }
        })?;

        Ok(())
    }

    /// 渲染消息区域
    fn render_messages(frame: &mut Frame, area: Rect, app_state: &AppState) {
        let messages = app_state.current_messages();

        // 计算可见消息范围
        let visible_height = area.height.saturating_sub(2); // 减去边框
        let start = if app_state.scroll_offset < messages.len() {
            app_state.scroll_offset
        } else {
            messages.len().saturating_sub(visible_height as usize)
        };
        let end = (start + visible_height as usize).min(messages.len());

        let visible_messages = if start < messages.len() {
            &messages[start..end]
        } else {
            &messages[0..0]
        };

        // 创建消息显示组件
        let message_display = MessageDisplay::new(
            visible_messages,
            &app_state.theme,
            &app_state.settings,
            0,
            visible_height,
        );

        let block = Block::default()
            .title("💬 对话")
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Cyan));

        frame.render_widget(&block, area);

        // 渲染消息内容
        let inner_area = block.inner(area);
        frame.render_widget(message_display, inner_area);

        // 如果有搜索高亮
        if app_state.is_searching && !app_state.search_query.is_empty() {
            Self::render_search_highlight(
                frame,
                inner_area,
                &visible_messages,
                &app_state.search_query,
            );
        }
    }

    /// 渲染搜索高亮
    fn render_search_highlight(frame: &mut Frame, area: Rect, messages: &[&Message], query: &str) {
        // 简化处理：实际应该高亮匹配文本
        // 这里只是添加一个搜索状态提示
        let search_status = format!("🔍 搜索: {} (匹配: {})", query, messages.len());
        let paragraph = Paragraph::new(search_status).style(Style::default().fg(Color::Yellow));

        frame.render_widget(paragraph, area);
    }

    /// 渲染输入区域
    fn render_input(frame: &mut Frame, area: Rect, app_state: &AppState) {
        let input_box = InputBox::new(
            &app_state.input,
            app_state.input_cursor,
            &app_state.settings.prompt_prefix,
            &app_state.theme,
        );

        frame.render_widget(input_box, area);

        // 如果正在生成，显示状态
        if app_state.is_generating {
            let status = Paragraph::new("⏳ 正在生成...").style(Style::default().fg(Color::Yellow));
            frame.render_widget(status, area);
        }
    }

    /// 渲染侧边栏
    fn render_sidebar(frame: &mut Frame, area: Rect, app_state: &AppState) {
        let selected_index = app_state.sessions.iter().position(|s| {
            app_state
                .current_session
                .as_ref()
                .map(|cs| cs.id == s.id)
                .unwrap_or(false)
        });

        let session_list = SessionList::new(&app_state.sessions, selected_index, &app_state.theme);

        frame.render_widget(session_list, area);
    }

    /// 渲染状态行
    fn render_status_bar(frame: &mut Frame, area: Rect, app_state: &AppState) {
        let current_title = app_state.current_session.as_ref().map(|s| s.title.as_str());

        let status_bar = StatusBar::new(
            &app_state.mode,
            current_title,
            app_state.is_generating,
            app_state.current_messages().len(),
            &app_state.theme,
        );

        // 状态行在底部
        let status_area = Rect::new(area.left(), area.bottom() - 1, area.width, 1);
        frame.render_widget(status_bar, status_area);
    }

    /// 渲染帮助面板
    fn render_help_overlay(frame: &mut Frame, area: Rect, theme: &crate::state::Theme) {
        // 创建半透明背景
        let block = Block::default().style(
            Style::default()
                .bg(Color::Black)
                .add_modifier(Modifier::DIM),
        );
        frame.render_widget(Clear, area);
        frame.render_widget(block, area);

        // 居中显示帮助面板
        let help_area = Self::centered_rect(60, 80, area);
        let help_panel = HelpPanel::new(theme.clone());
        frame.render_widget(help_panel, help_area);
    }

    /// 渲染设置面板
    fn render_settings_overlay(
        frame: &mut Frame,
        area: Rect,
        theme: &crate::state::Theme,
        settings: &crate::state::Settings,
    ) {
        let block = Block::default()
            .title("⚙️ 设置")
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Yellow));

        frame.render_widget(Clear, area);
        let inner_area = block.inner(area);
        frame.render_widget(&block, area);

        let settings_text = format!(
            "显示状态行: {}\n\
             显示时间戳: {}\n\
             显示工具详情: {}\n\
             自动滚动: {}\n\
             语法高亮: {}\n\
             启用鼠标: {}\n\
             主题: {}\n\
             提示前缀: {}",
            settings.show_status_line,
            settings.show_timestamp,
            settings.show_tool_details,
            settings.auto_scroll,
            settings.syntax_highlight,
            settings.enable_mouse,
            settings.theme_name,
            settings.prompt_prefix,
        );

        let paragraph = Paragraph::new(settings_text).style(Style::default().fg(Color::White));

        frame.render_widget(paragraph, inner_area);
    }

    /// 渲染历史面板
    fn render_history_overlay(
        frame: &mut Frame,
        area: Rect,
        theme: &crate::state::Theme,
        sessions: &[crate::state::Session],
    ) {
        let block = Block::default()
            .title("📜 历史")
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Blue));

        frame.render_widget(Clear, area);
        let inner_area = block.inner(area);
        frame.render_widget(&block, area);

        // 显示所有会话
        let items: Vec<ListItem> = sessions
            .iter()
            .map(|session| {
                let timestamp =
                    chrono::DateTime::from_timestamp(session.created_at as i64 / 1000, 0)
                        .map(|dt| dt.format("%Y-%m-%d %H:%M").to_string())
                        .unwrap_or_default();

                ListItem::new(Line::from(format!(
                    "{} - {} ({})",
                    session.title,
                    timestamp,
                    session.messages.len()
                )))
            })
            .collect();

        let list = List::new(items);
        frame.render_widget(list, inner_area);
    }

    /// 创建居中矩形
    fn centered_rect(percent_x: u16, percent_y: u16, area: Rect) -> Rect {
        let layout = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Percentage((100 - percent_y) / 2),
                Constraint::Percentage(percent_y),
                Constraint::Percentage((100 - percent_y) / 2),
            ])
            .split(area);

        let vertical_margin = layout[1];

        let layout = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([
                Constraint::Percentage((100 - percent_x) / 2),
                Constraint::Percentage(percent_x),
                Constraint::Percentage((100 - percent_x) / 2),
            ])
            .split(vertical_margin);

        layout[1]
    }
}

impl Default for TuiRenderer {
    fn default() -> Self {
        Self::new().unwrap()
    }
}
