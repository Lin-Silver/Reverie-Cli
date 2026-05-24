//! 沙箱管理器
//!
//! 管理沙箱实例的创建、监控和销毁

use crate::policy::{
    AuditEvent, AuditEventDetails, AuditEventType, AuditResult, SandboxError, SandboxPolicy,
};
use crate::SandboxResult;
use std::collections::HashMap;
use std::process::{Child, Command, Stdio};

/// 沙箱实例
pub struct SandboxInstance {
    /// 实例 ID
    pub id: String,
    /// 沙箱策略
    pub policy: SandboxPolicy,
    /// 子进程（如果已启动）
    pub process: Option<Child>,
    /// 创建时间
    pub created_at: u64,
    /// 审计日志
    pub audit_log: Vec<AuditEvent>,
}

impl SandboxInstance {
    /// 创建新的沙箱实例
    pub fn new(id: String, policy: SandboxPolicy) -> Self {
        Self {
            id,
            policy,
            process: None,
            created_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64,
            audit_log: Vec::new(),
        }
    }

    /// 记录审计事件
    fn log_audit(
        &mut self,
        event_type: AuditEventType,
        details: AuditEventDetails,
        result: AuditResult,
    ) {
        if self.policy.audit_logging {
            self.audit_log.push(AuditEvent {
                timestamp: std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_millis() as u64,
                event_type,
                details,
                result,
            });
        }
    }

    /// 检查文件访问权限
    pub fn check_file_access(
        &mut self,
        path: &std::path::Path,
        mode: crate::policy::FileAccessMode,
    ) -> SandboxResult<()> {
        let path_str = path.to_string_lossy();

        // 查找匹配的规则
        for rule in &self.policy.file_rules {
            if let Some(rule_mode) = rule.matches(path) {
                // 检查权限是否足够
                match (rule_mode, mode) {
                    (crate::policy::FileAccessMode::Deny, _) => {
                        self.log_audit(
                            AuditEventType::FileAccess,
                            AuditEventDetails {
                                path: Some(path_str.to_string()),
                                ..Default::default()
                            },
                            AuditResult::Denied,
                        );
                        return Err(SandboxError::PermissionDenied(format!(
                            "Access denied to: {}",
                            path_str
                        )));
                    }
                    (
                        crate::policy::FileAccessMode::Read,
                        crate::policy::FileAccessMode::ReadWrite,
                    )
                    | (crate::policy::FileAccessMode::Read, crate::policy::FileAccessMode::Write) =>
                    {
                        self.log_audit(
                            AuditEventType::FileAccess,
                            AuditEventDetails {
                                path: Some(path_str.to_string()),
                                ..Default::default()
                            },
                            AuditResult::Denied,
                        );
                        return Err(SandboxError::PermissionDenied(format!(
                            "Write access denied to: {}",
                            path_str
                        )));
                    }
                    _ => {
                        self.log_audit(
                            AuditEventType::FileAccess,
                            AuditEventDetails {
                                path: Some(path_str.to_string()),
                                ..Default::default()
                            },
                            AuditResult::Allowed,
                        );
                        return Ok(());
                    }
                }
            }
        }

        // 没有匹配的规则，默认拒绝
        self.log_audit(
            AuditEventType::FileAccess,
            AuditEventDetails {
                path: Some(path_str.to_string()),
                ..Default::default()
            },
            AuditResult::Denied,
        );
        Err(SandboxError::PermissionDenied(format!(
            "No rule for: {}",
            path_str
        )))
    }

    /// 检查网络访问权限
    pub fn check_network_access(&mut self, host: &str, port: Option<u16>) -> SandboxResult<()> {
        for rule in &self.policy.network_rules {
            if rule.matches(host) {
                if rule.allowed {
                    // 检查端口范围
                    if let Some((min_port, max_port)) = rule.ports {
                        if let Some(port) = port {
                            if port < min_port || port > max_port {
                                self.log_audit(
                                    AuditEventType::NetworkAccess,
                                    AuditEventDetails {
                                        host: Some(host.to_string()),
                                        port: Some(port),
                                        ..Default::default()
                                    },
                                    AuditResult::Denied,
                                );
                                return Err(SandboxError::NetworkAccessDenied(format!(
                                    "Port {} not allowed for host: {}",
                                    port, host
                                )));
                            }
                        }
                    }

                    self.log_audit(
                        AuditEventType::NetworkAccess,
                        AuditEventDetails {
                            host: Some(host.to_string()),
                            port,
                            ..Default::default()
                        },
                        AuditResult::Allowed,
                    );
                    return Ok(());
                } else {
                    self.log_audit(
                        AuditEventType::NetworkAccess,
                        AuditEventDetails {
                            host: Some(host.to_string()),
                            port,
                            ..Default::default()
                        },
                        AuditResult::Denied,
                    );
                    return Err(SandboxError::NetworkAccessDenied(format!(
                        "Access denied to: {}",
                        host
                    )));
                }
            }
        }

        // 没有匹配的规则，默认拒绝
        self.log_audit(
            AuditEventType::NetworkAccess,
            AuditEventDetails {
                host: Some(host.to_string()),
                port,
                ..Default::default()
            },
            AuditResult::Denied,
        );
        Err(SandboxError::NetworkAccessDenied(format!(
            "No rule for: {}",
            host
        )))
    }

    /// 检查命令是否允许
    pub fn check_command(&self, command: &str) -> SandboxResult<()> {
        let command_keys = command_policy_keys(command);

        // 检查禁止的命令
        if command_keys
            .iter()
            .any(|key| self.policy.process_limits.denied_commands.contains(key))
        {
            return Err(SandboxError::PermissionDenied(format!(
                "Command '{}' is denied",
                command
            )));
        }

        // 如果没有允许的命令列表，或者命令在允许列表中
        if self.policy.process_limits.allowed_commands.is_empty()
            || command_keys
                .iter()
                .any(|key| self.policy.process_limits.allowed_commands.contains(key))
            || command_keys
                .iter()
                .any(|key| is_development_toolchain_command(key))
        {
            return Ok(());
        }

        Err(SandboxError::PermissionDenied(format!(
            "Command '{}' is not allowed",
            command
        )))
    }

    /// 启动子进程
    pub fn spawn(&mut self, command: &str, args: &[&str]) -> SandboxResult<()> {
        // 检查命令是否允许
        self.check_command(command)?;

        // 创建进程
        let child = Command::new(command)
            .args(args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()?;

        self.process = Some(child);

        self.log_audit(
            AuditEventType::ProcessSpawn,
            AuditEventDetails {
                command: Some(format!("{} {}", command, args.join(" "))),
                ..Default::default()
            },
            AuditResult::Allowed,
        );

        Ok(())
    }

    /// 获取审计日志
    pub fn get_audit_log(&self) -> &[AuditEvent] {
        &self.audit_log
    }

    /// 清理审计日志
    pub fn clear_audit_log(&mut self) {
        self.audit_log.clear();
    }
}

fn command_policy_keys(command: &str) -> Vec<String> {
    let basename = command
        .trim()
        .trim_matches('"')
        .trim_matches('\'')
        .rsplit(['/', '\\'])
        .next()
        .unwrap_or(command)
        .trim();
    let lowercase = basename.to_ascii_lowercase();
    let mut keys = vec![command.to_string(), basename.to_string(), lowercase.clone()];
    for suffix in [".exe", ".cmd"] {
        if let Some(stripped) = lowercase.strip_suffix(suffix) {
            keys.push(stripped.to_string());
        }
    }
    keys.sort();
    keys.dedup();
    keys
}

fn is_development_toolchain_command(command: &str) -> bool {
    matches!(
        command.to_ascii_lowercase().as_str(),
        "node"
            | "node.exe"
            | "npm"
            | "npm.cmd"
            | "npm.exe"
            | "npx"
            | "npx.cmd"
            | "npx.exe"
            | "pnpm"
            | "pnpm.cmd"
            | "pnpm.exe"
            | "yarn"
            | "yarn.cmd"
            | "yarn.exe"
            | "corepack"
            | "corepack.cmd"
            | "corepack.exe"
            | "bun"
            | "bun.exe"
            | "deno"
            | "deno.exe"
            | "cargo"
            | "cargo.exe"
            | "rustc"
            | "rustc.exe"
            | "rustup"
            | "rustup.exe"
            | "rustfmt"
            | "rustfmt.exe"
            | "clippy-driver"
            | "clippy-driver.exe"
            | "docker"
            | "docker.exe"
            | "docker-compose"
            | "docker-compose.exe"
            | "podman"
            | "podman.exe"
            | "nerdctl"
            | "nerdctl.exe"
    )
}

/// 沙箱管理器
pub struct SandboxManager {
    /// 沙箱实例
    instances: HashMap<String, SandboxInstance>,
    /// 默认策略
    default_policy: SandboxPolicy,
}

impl SandboxManager {
    /// 创建新的沙箱管理器
    pub fn new() -> Self {
        Self {
            instances: HashMap::new(),
            default_policy: SandboxPolicy::default(),
        }
    }

    /// 创建新的沙箱实例
    pub fn create_sandbox(
        &mut self,
        id: Option<String>,
        policy: Option<SandboxPolicy>,
    ) -> SandboxResult<String> {
        let id = id.unwrap_or_else(|| format!("sandbox-{}", chrono::Utc::now().timestamp_millis()));
        let policy = policy.unwrap_or_else(|| self.default_policy.clone());

        let instance = SandboxInstance::new(id.clone(), policy);
        self.instances.insert(id.clone(), instance);

        Ok(id)
    }

    /// 获取沙箱实例
    pub fn get_sandbox(&self, id: &str) -> Option<&SandboxInstance> {
        self.instances.get(id)
    }

    /// 获取沙箱实例（可变）
    pub fn get_sandbox_mut(&mut self, id: &str) -> Option<&mut SandboxInstance> {
        self.instances.get_mut(id)
    }

    /// 删除沙箱实例
    pub fn delete_sandbox(&mut self, id: &str) -> SandboxResult<()> {
        if let Some(instance) = self.instances.remove(id) {
            // 终止进程
            if let Some(mut process) = instance.process {
                let _ = process.kill();
            }
        }

        Ok(())
    }

    /// 列出所有沙箱实例
    pub fn list_sandboxes(&self) -> Vec<&SandboxInstance> {
        self.instances.values().collect()
    }

    /// 设置默认策略
    pub fn set_default_policy(&mut self, policy: SandboxPolicy) {
        self.default_policy = policy;
    }

    /// 获取默认策略
    pub fn get_default_policy(&self) -> &SandboxPolicy {
        &self.default_policy
    }
}

impl Default for SandboxManager {
    fn default() -> Self {
        Self::new()
    }
}
