//! 沙箱策略定义
//!
//! 定义沙箱的安全策略、限制和规则

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

/// 沙箱策略
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SandboxPolicy {
    /// 策略名称
    pub name: String,
    /// 是否启用
    pub enabled: bool,
    /// 文件访问规则
    pub file_rules: Vec<FileRule>,
    /// 网络访问规则
    pub network_rules: Vec<NetworkRule>,
    /// 进程限制
    pub process_limits: ProcessLimits,
    /// 环境变量
    pub env_vars: HashMap<String, String>,
    /// 资源限制
    pub resource_limits: ResourceLimits,
    /// 审计日志
    pub audit_logging: bool,
}

impl Default for SandboxPolicy {
    fn default() -> Self {
        Self {
            name: "default".to_string(),
            enabled: true,
            file_rules: vec![
                FileRule::allow_read("/tmp"),
                FileRule::allow_read_write("/tmp/reverie"),
                FileRule::deny_all(),
            ],
            network_rules: vec![NetworkRule::allow("localhost"), NetworkRule::deny_all()],
            process_limits: ProcessLimits::default(),
            env_vars: HashMap::new(),
            resource_limits: ResourceLimits::default(),
            audit_logging: true,
        }
    }
}

/// 文件访问规则
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileRule {
    /// 路径模式
    pub path: String,
    /// 访问模式
    pub mode: FileAccessMode,
    /// 是否递归
    pub recursive: bool,
}

/// 文件访问模式
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum FileAccessMode {
    /// 拒绝所有
    Deny,
    /// 只读
    Read,
    /// 读写
    ReadWrite,
    /// 只写
    Write,
}

impl FileRule {
    /// 创建允许读取的规则
    pub fn allow_read(path: &str) -> Self {
        Self {
            path: path.to_string(),
            mode: FileAccessMode::Read,
            recursive: true,
        }
    }

    /// 创建允许读写的规则
    pub fn allow_read_write(path: &str) -> Self {
        Self {
            path: path.to_string(),
            mode: FileAccessMode::ReadWrite,
            recursive: true,
        }
    }

    /// 创建拒绝所有的规则
    pub fn deny_all() -> Self {
        Self {
            path: "/".to_string(),
            mode: FileAccessMode::Deny,
            recursive: true,
        }
    }

    /// 检查路径是否匹配规则
    pub fn matches(&self, path: &Path) -> Option<FileAccessMode> {
        let path_str = path.to_string_lossy();

        if self.path == "/" {
            return Some(self.mode);
        }

        if path_str.starts_with(&self.path) {
            return Some(self.mode);
        }

        None
    }
}

/// 网络访问规则
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetworkRule {
    /// 主机模式
    pub host: String,
    /// 端口范围
    pub ports: Option<(u16, u16)>,
    /// 是否允许
    pub allowed: bool,
}

impl NetworkRule {
    /// 创建允许规则
    pub fn allow(host: &str) -> Self {
        Self {
            host: host.to_string(),
            ports: None,
            allowed: true,
        }
    }

    /// 创建拒绝规则
    pub fn deny(host: &str) -> Self {
        Self {
            host: host.to_string(),
            ports: None,
            allowed: false,
        }
    }

    /// 创建拒绝所有规则
    pub fn deny_all() -> Self {
        Self {
            host: "*".to_string(),
            ports: None,
            allowed: false,
        }
    }

    /// 检查主机是否匹配规则
    pub fn matches(&self, host: &str) -> bool {
        if self.host == "*" {
            return true;
        }

        if self.host == host {
            return true;
        }

        // 简单的通配符匹配
        if self.host.starts_with("*.") {
            let domain = &self.host[2..];
            return host.ends_with(domain);
        }

        false
    }
}

/// 进程限制
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessLimits {
    /// 最大进程数
    pub max_processes: Option<u32>,
    /// 最大线程数
    pub max_threads: Option<u32>,
    /// CPU 时间限制（秒）
    pub cpu_time_limit: Option<u64>,
    /// 内存限制（字节）
    pub memory_limit: Option<u64>,
    /// 允许的命令
    pub allowed_commands: HashSet<String>,
    /// 禁止的命令
    pub denied_commands: HashSet<String>,
}

impl Default for ProcessLimits {
    fn default() -> Self {
        Self {
            max_processes: Some(10),
            max_threads: Some(100),
            cpu_time_limit: Some(300),
            memory_limit: Some(512 * 1024 * 1024), // 512MB
            allowed_commands: HashSet::new(),
            denied_commands: HashSet::new(),
        }
    }
}

/// 资源限制
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceLimits {
    /// 最大文件描述符数
    pub max_open_files: Option<u32>,
    /// 最大信号数
    pub max_signals: Option<u32>,
    /// 最大锁数
    pub max_locks: Option<u32>,
    /// 最大消息队列数
    pub max_msg_queue: Option<u32>,
    /// 最大共享内存段
    pub max_shm_segments: Option<u32>,
}

impl Default for ResourceLimits {
    fn default() -> Self {
        Self {
            max_open_files: Some(1024),
            max_signals: Some(64),
            max_locks: Some(100),
            max_msg_queue: Some(10),
            max_shm_segments: Some(10),
        }
    }
}

/// 沙箱审计事件
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEvent {
    /// 时间戳
    pub timestamp: u64,
    /// 事件类型
    pub event_type: AuditEventType,
    /// 详情
    pub details: AuditEventDetails,
    /// 结果
    pub result: AuditResult,
}

/// 审计事件类型
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum AuditEventType {
    FileAccess,
    NetworkAccess,
    ProcessSpawn,
    ResourceLimit,
    EnvAccess,
    PermissionDenied,
}

/// 审计事件详情
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AuditEventDetails {
    /// 路径（文件访问）
    pub path: Option<String>,
    /// 主机（网络访问）
    pub host: Option<String>,
    /// 端口（网络访问）
    pub port: Option<u16>,
    /// 命令（进程）
    pub command: Option<String>,
    /// 资源类型
    pub resource_type: Option<String>,
    /// 资源值
    pub resource_value: Option<u64>,
    /// 错误信息
    pub error: Option<String>,
}

/// 审计结果
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum AuditResult {
    Allowed,
    Denied,
    Error,
}

/// 沙箱错误
#[derive(Debug)]
pub enum SandboxError {
    PermissionDenied(String),
    ResourceLimitExceeded(String),
    InvalidPath(String),
    NetworkAccessDenied(String),
    ProcessLimitExceeded,
    IoError(std::io::Error),
}

impl std::fmt::Display for SandboxError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SandboxError::PermissionDenied(msg) => write!(f, "Permission denied: {}", msg),
            SandboxError::ResourceLimitExceeded(msg) => {
                write!(f, "Resource limit exceeded: {}", msg)
            }
            SandboxError::InvalidPath(msg) => write!(f, "Invalid path: {}", msg),
            SandboxError::NetworkAccessDenied(msg) => write!(f, "Network access denied: {}", msg),
            SandboxError::ProcessLimitExceeded => write!(f, "Process limit exceeded"),
            SandboxError::IoError(e) => write!(f, "IO error: {}", e),
        }
    }
}

impl std::error::Error for SandboxError {}

impl From<std::io::Error> for SandboxError {
    fn from(e: std::io::Error) -> Self {
        SandboxError::IoError(e)
    }
}
