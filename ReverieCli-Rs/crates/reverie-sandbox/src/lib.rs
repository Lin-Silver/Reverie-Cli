//! Reverie 沙箱 - 安全执行环境
//! 
//! 提供进程隔离、资源限制和安全策略执行

pub mod policy;
pub mod manager;

#[cfg(windows)]
pub mod windows;

#[cfg(unix)]
pub mod unix;

pub use policy::{SandboxPolicy, SandboxError};
pub use manager::SandboxManager;

/// 沙箱结果
pub type SandboxResult<T> = Result<T, SandboxError>;
