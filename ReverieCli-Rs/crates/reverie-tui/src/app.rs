//! TUI 主应用
//!
//! 整合事件处理、状态管理和渲染

use crossterm::{
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use std::sync::mpsc::{Receiver, Sender};
use tokio::sync::mpsc as async_mpsc;

use crate::event::Event;
use crate::handler::EventHandler;
use crate::render::TuiRenderer;
use crate::state::AppState;

/// TUI 应用
pub struct TuiApp {
    /// 应用状态
    app_state: AppState,
    /// 事件处理器
    event_handler: EventHandler,
    /// TUI 渲染器
    renderer: TuiRenderer,
    /// 事件接收器
    event_rx: Receiver<Event>,
    /// 事件发送器
    event_tx: Sender<Event>,
    /// 异步事件通道
    async_event_tx: Option<async_mpsc::Sender<Event>>,
    /// 是否退出
    should_quit: bool,
}

impl TuiApp {
    /// 创建新的 TUI 应用
    pub fn new(mode: String) -> Result<Self, Box<dyn std::error::Error>> {
        let app_state = AppState::new(mode);
        let event_handler = EventHandler::new(app_state.clone());
        let renderer = TuiRenderer::new()?;
        let (event_tx, event_rx) = std::sync::mpsc::channel();

        Ok(Self {
            app_state,
            event_handler,
            renderer,
            event_rx,
            event_tx,
            async_event_tx: None,
            should_quit: false,
        })
    }

    /// 设置异步事件通道
    pub fn set_async_event_tx(&mut self, tx: async_mpsc::Sender<Event>) {
        self.async_event_tx = Some(tx);
    }

    /// 获取应用状态引用
    pub fn app_state(&self) -> &AppState {
        &self.app_state
    }

    /// 获取应用状态可变引用
    pub fn app_state_mut(&mut self) -> &mut AppState {
        &mut self.app_state
    }

    /// 运行应用主循环
    pub fn run(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        // 启用终端
        enable_raw_mode()?;
        execute!(std::io::stdout(), EnterAlternateScreen)?;

        // 创建初始会话
        self.app_state.create_session("新会话".to_string());

        // 主循环
        loop {
            // 渲染
            self.renderer.render(&self.app_state)?;

            // 处理事件
            match self.event_handler.next() {
                Ok(Event::Quit) => {
                    self.should_quit = true;
                    break;
                }
                Ok(event) => {
                    self.event_handler.handle_event(event);
                }
                Err(_) => {}
            }

            // 检查退出标志
            if self.should_quit || self.event_handler.should_quit() {
                break;
            }

            // 处理异步事件（如果存在）
            if let Some(_tx) = &self.async_event_tx {
                // 这里可以处理来自异步任务的事件
            }
        }

        // 恢复终端
        self.shutdown()?;

        Ok(())
    }

    /// 发送事件
    pub fn send_event(&self, event: Event) -> Result<(), Box<dyn std::error::Error>> {
        self.event_tx.send(event)?;
        Ok(())
    }

    /// 添加消息
    pub fn add_message(&mut self, content: String, role: crate::state::MessageRole) {
        let message = crate::state::Message::new(role, content);
        self.app_state.add_message(message);
    }

    /// 添加工具调用
    pub fn add_tool_call(&mut self, tool_name: String, args: serde_json::Value) {
        self.event_handler
            .handle_event(Event::ToolCall { tool_name, args });
    }

    /// 添加工具结果
    pub fn add_tool_result(&mut self, tool_name: String, result: Result<String, String>) {
        self.event_handler
            .handle_event(Event::ToolResult { tool_name, result });
    }

    /// 设置生成状态
    pub fn set_generating(&mut self, generating: bool) {
        self.app_state.is_generating = generating;
    }

    /// 切换会话
    pub fn switch_session(&mut self, session_id: &str) {
        self.app_state.switch_session(session_id);
    }

    /// 创建新会话
    pub fn create_session(&mut self, title: String) -> String {
        self.app_state.create_session(title)
    }

    /// 删除会话
    pub fn delete_session(&mut self, session_id: &str) {
        self.app_state.delete_session(session_id);
    }

    /// 清屏
    pub fn clear_screen(&mut self) {
        self.app_state.scroll_offset = 0;
    }

    /// 显示帮助
    pub fn show_help(&mut self) {
        self.app_state.show_help = true;
    }

    /// 显示设置
    pub fn show_settings(&mut self) {
        self.app_state.show_settings = true;
    }

    /// 显示历史
    pub fn show_history(&mut self) {
        self.app_state.show_history = true;
    }

    /// 开始搜索
    pub fn start_search(&mut self) {
        self.app_state.is_searching = true;
        self.app_state.search_query.clear();
    }

    /// 停止生成
    pub fn stop_generation(&mut self) {
        self.app_state.is_generating = false;
    }

    /// 重新生成
    pub fn regenerate(&mut self) {
        // 触发重新生成逻辑
    }

    /// 关闭应用
    pub fn shutdown(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        disable_raw_mode()?;
        execute!(std::io::stdout(), LeaveAlternateScreen)?;
        Ok(())
    }
}

impl Drop for TuiApp {
    fn drop(&mut self) {
        let _ = self.shutdown();
    }
}
