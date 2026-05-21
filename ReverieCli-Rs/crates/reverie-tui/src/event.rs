//! 事件系统 - 定义 TUI 中所有的事件类型

use crossterm::event::{self, Event as CrosstermEvent, KeyEvent, MouseEvent};
use std::time::Duration;

/// TUI 事件类型
#[derive(Debug, Clone)]
pub enum Event {
    /// 终端原始事件
    Terminal(CrosstermEvent),

    /// 键盘事件
    Key(KeyEvent),

    /// 鼠标事件
    Mouse(MouseEvent),

    /// 窗口大小改变
    Resize(u16, u16),

    /// 刷新界面
    Refresh,

    /// 停止事件循环
    Quit,

    /// 发送消息
    SendMessage(String),

    /// 选择会话
    SelectSession(String),

    /// 切换模式
    SwitchMode(String),

    /// 工具调用
    ToolCall {
        tool_name: String,
        args: serde_json::Value,
    },

    /// 工具结果
    ToolResult {
        tool_name: String,
        result: Result<String, String>,
    },

    /// 显示帮助
    ShowHelp,

    /// 显示设置
    ShowSettings,

    /// 显示会话历史
    ShowHistory,

    /// 清除屏幕
    ClearScreen,

    /// 复制内容
    CopyContent(String),

    /// 保存会话
    SaveSession,

    /// 加载会话
    LoadSession,

    /// 删除会话
    DeleteSession(String),

    /// 重新生成响应
    Regenerate,

    /// 停止生成
    StopGeneration,

    /// 滚动到顶部
    ScrollToTop,

    /// 滚动到底部
    ScrollToBottom,

    /// 搜索内容
    Search(String),

    /// 下一个搜索结果
    NextSearchResult,

    /// 上一个搜索结果
    PreviousSearchResult,

    /// 取消搜索
    CancelSearch,
}

impl From<CrosstermEvent> for Event {
    fn from(event: CrosstermEvent) -> Self {
        match event {
            CrosstermEvent::Key(key) => Event::Key(key),
            CrosstermEvent::Mouse(mouse) => Event::Mouse(mouse),
            CrosstermEvent::Resize(w, h) => Event::Resize(w, h),
            CrosstermEvent::FocusGained => Event::Refresh,
            CrosstermEvent::FocusLost => Event::Refresh,
            _ => Event::Terminal(event),
        }
    }
}

/// 事件处理器
pub struct EventHandler {
    /// 事件通道发送器
    tx: std::sync::mpsc::Sender<Event>,
    /// 事件通道接收器
    rx: std::sync::mpsc::Receiver<Event>,
    /// 是否退出
    should_quit: bool,
    /// 事件处理间隔
    tick_rate: Duration,
}

impl EventHandler {
    /// 创建新的事件处理器
    pub fn new(tick_rate: Option<Duration>) -> Self {
        let tick_rate = tick_rate.unwrap_or(Duration::from_millis(250));
        let (tx, rx) = std::sync::mpsc::channel();

        Self {
            tx,
            rx,
            should_quit: false,
            tick_rate,
        }
    }

    /// 获取下一个事件
    pub fn next(&self) -> Result<Event, Box<dyn std::error::Error>> {
        // 等待事件或超时
        loop {
            // 检查是否有待处理事件
            if let Ok(event) = self.rx.try_recv() {
                return Ok(event);
            }

            // 检查是否应该退出
            if self.should_quit {
                return Ok(Event::Quit);
            }

            // 等待一段时间
            std::thread::sleep(Duration::from_millis(10));
        }
    }

    /// 发送事件
    pub fn send(&self, event: Event) -> Result<(), Box<dyn std::error::Error>> {
        self.tx.send(event)?;
        Ok(())
    }

    /// 处理 crossterm 事件
    pub fn poll(&mut self) -> Result<bool, Box<dyn std::error::Error>> {
        let has_event = event::poll(Duration::from_millis(100))?;

        if has_event {
            if let CrosstermEvent::Key(key) = event::read()? {
                // 检查退出键
                if key.code == event::KeyCode::Char('q')
                    && key.modifiers.contains(event::KeyModifiers::CONTROL)
                {
                    self.should_quit = true;
                }

                // 发送键盘事件
                self.send(Event::Key(key))?;
            }
        }

        Ok(has_event)
    }

    /// 检查是否应该退出
    pub fn should_quit(&self) -> bool {
        self.should_quit
    }

    /// 设置退出标志
    pub fn set_should_quit(&mut self, quit: bool) {
        self.should_quit = quit;
    }

    /// 获取 tick 率
    pub fn tick_rate(&self) -> Duration {
        self.tick_rate
    }
}

/// 键盘快捷键
pub mod keys {
    use crossterm::event::{KeyCode, KeyModifiers};

    /// 退出 (Ctrl+Q)
    pub const QUIT: (KeyCode, KeyModifiers) = (KeyCode::Char('q'), KeyModifiers::CONTROL);

    /// 帮助 (F1)
    pub const HELP: (KeyCode, KeyModifiers) = (KeyCode::F(1), KeyModifiers::NONE);

    /// 设置 (F2)
    pub const SETTINGS: (KeyCode, KeyModifiers) = (KeyCode::F(2), KeyModifiers::NONE);

    /// 历史 (F3)
    pub const HISTORY: (KeyCode, KeyModifiers) = (KeyCode::F(3), KeyModifiers::NONE);

    /// 发送消息 (Enter)
    pub const SEND: (KeyCode, KeyModifiers) = (KeyCode::Enter, KeyModifiers::NONE);

    /// 停止生成 (Ctrl+C)
    pub const STOP: (KeyCode, KeyModifiers) = (KeyCode::Char('c'), KeyModifiers::CONTROL);

    /// 重新生成 (Ctrl+R)
    pub const REGENERATE: (KeyCode, KeyModifiers) = (KeyCode::Char('r'), KeyModifiers::CONTROL);

    /// 搜索 (Ctrl+F)
    pub const SEARCH: (KeyCode, KeyModifiers) = (KeyCode::Char('f'), KeyModifiers::CONTROL);

    /// 下一个搜索结果 (F3 或 Tab)
    pub const NEXT_SEARCH: (KeyCode, KeyModifiers) = (KeyCode::F(3), KeyModifiers::NONE);

    /// 上一个搜索结果 (Shift+F3 或 Shift+Tab)
    pub const PREV_SEARCH: (KeyCode, KeyModifiers) = (KeyCode::F(3), KeyModifiers::SHIFT);

    /// 复制 (Ctrl+Shift+C)
    pub fn copy() -> (KeyCode, KeyModifiers) {
        (
            KeyCode::Char('c'),
            KeyModifiers::CONTROL | KeyModifiers::SHIFT,
        )
    }

    /// 保存会话 (Ctrl+S)
    pub const SAVE: (KeyCode, KeyModifiers) = (KeyCode::Char('s'), KeyModifiers::CONTROL);

    /// 加载会话 (Ctrl+L)
    pub const LOAD: (KeyCode, KeyModifiers) = (KeyCode::Char('l'), KeyModifiers::CONTROL);

    /// 删除会话 (Ctrl+D)
    pub const DELETE: (KeyCode, KeyModifiers) = (KeyCode::Char('d'), KeyModifiers::CONTROL);

    /// 滚动到顶部 (Home 或 Ctrl+Home)
    pub const SCROLL_TOP: (KeyCode, KeyModifiers) = (KeyCode::Home, KeyModifiers::NONE);

    /// 滚动到底部 (End 或 Ctrl+End)
    pub const SCROLL_BOTTOM: (KeyCode, KeyModifiers) = (KeyCode::End, KeyModifiers::NONE);

    /// 上一个会话 (Ctrl+PageUp)
    pub const PREV_SESSION: (KeyCode, KeyModifiers) = (KeyCode::PageUp, KeyModifiers::CONTROL);

    /// 下一个会话 (Ctrl+PageDown)
    pub const NEXT_SESSION: (KeyCode, KeyModifiers) = (KeyCode::PageDown, KeyModifiers::CONTROL);

    /// 切换模式 (Ctrl+M)
    pub const SWITCH_MODE: (KeyCode, KeyModifiers) = (KeyCode::Char('m'), KeyModifiers::CONTROL);

    /// 清除屏幕 (Ctrl+L)
    pub const CLEAR_SCREEN: (KeyCode, KeyModifiers) = (KeyCode::Char('l'), KeyModifiers::CONTROL);

    /// 确认 (Enter)
    pub const CONFIRM: (KeyCode, KeyModifiers) = (KeyCode::Enter, KeyModifiers::NONE);

    /// 取消 (Escape)
    pub const CANCEL: (KeyCode, KeyModifiers) = (KeyCode::Esc, KeyModifiers::NONE);

    /// 向上 (Up 或 k)
    pub const UP: (KeyCode, KeyModifiers) = (KeyCode::Up, KeyModifiers::NONE);

    /// 向下 (Down 或 j)
    pub const DOWN: (KeyCode, KeyModifiers) = (KeyCode::Down, KeyModifiers::NONE);

    /// 向左 (Left 或 h)
    pub const LEFT: (KeyCode, KeyModifiers) = (KeyCode::Left, KeyModifiers::NONE);

    /// 向右 (Right 或 l)
    pub const RIGHT: (KeyCode, KeyModifiers) = (KeyCode::Right, KeyModifiers::NONE);

    /// 检查是否是快捷键
    pub fn is_key(
        key_code: KeyCode,
        modifiers: KeyModifiers,
        key: (KeyCode, KeyModifiers),
    ) -> bool {
        key_code == key.0 && modifiers == key.1
    }
}
