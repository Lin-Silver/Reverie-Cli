//! Reverie TUI - 终端用户界面
//!
//! 提供丰富的终端界面，支持：
//! - 响应流式显示
//! - 工具调用可视化
//! - 会话管理
//! - 键盘快捷操作
//! - 主题和样式

pub mod app;
pub mod components;
pub mod event;
pub mod handler;
pub mod render;
pub mod state;

pub use app::TuiApp;
pub use event::Event;
pub use handler::EventHandler;
