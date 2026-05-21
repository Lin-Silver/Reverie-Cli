//! Sandbox 测试

#[cfg(test)]
mod tests {
    use reverie_sandbox::manager::{SandboxInstance, SandboxManager};
    use reverie_sandbox::policy::{
        AuditEventType, AuditResult, FileAccessMode, FileRule, NetworkRule, ProcessLimits,
        ResourceLimits, SandboxPolicy,
    };

    #[test]
    fn test_default_policy() {
        let policy = SandboxPolicy::default();
        assert!(policy.enabled);
        assert_eq!(policy.name, "default");
        assert!(policy.audit_logging);
    }

    #[test]
    fn test_file_rule_allow_read() {
        let rule = FileRule::allow_read("/tmp");
        assert_eq!(rule.mode, FileAccessMode::Read);
        assert!(rule.recursive);

        // 测试匹配
        let path = std::path::Path::new("/tmp/test/file.txt");
        assert_eq!(rule.matches(path), Some(FileAccessMode::Read));

        // 测试不匹配
        let path = std::path::Path::new("/home/user/file.txt");
        assert_eq!(rule.matches(path), None);
    }

    #[test]
    fn test_file_rule_deny_all() {
        let rule = FileRule::deny_all();
        assert_eq!(rule.mode, FileAccessMode::Deny);

        let path = std::path::Path::new("/any/path");
        assert_eq!(rule.matches(path), Some(FileAccessMode::Deny));
    }

    #[test]
    fn test_network_rule_allow() {
        let rule = NetworkRule::allow("localhost");
        assert!(rule.allowed);

        assert!(rule.matches("localhost"));
        assert!(!rule.matches("example.com"));
    }

    #[test]
    fn test_network_rule_deny_all() {
        let rule = NetworkRule::deny_all();
        assert!(!rule.allowed);

        assert!(rule.matches("any.host"));
    }

    #[test]
    fn test_process_limits_default() {
        let limits = ProcessLimits::default();
        assert_eq!(limits.max_processes, Some(10));
        assert_eq!(limits.max_threads, Some(100));
        assert_eq!(limits.cpu_time_limit, Some(300));
        assert_eq!(limits.memory_limit, Some(512 * 1024 * 1024));
    }

    #[test]
    fn test_resource_limits_default() {
        let limits = ResourceLimits::default();
        assert_eq!(limits.max_open_files, Some(1024));
        assert_eq!(limits.max_signals, Some(64));
    }

    #[test]
    fn test_sandbox_manager_creation() {
        let manager = SandboxManager::new();
        assert!(manager.list_sandboxes().is_empty());
    }

    #[test]
    fn test_create_sandbox() {
        let mut manager = SandboxManager::new();
        let id = manager.create_sandbox(None, None).unwrap();

        assert!(id.starts_with("sandbox-"));
        assert_eq!(manager.list_sandboxes().len(), 1);
    }

    #[test]
    fn test_create_sandbox_with_custom_id() {
        let mut manager = SandboxManager::new();
        let id = manager
            .create_sandbox(Some("my-sandbox".to_string()), None)
            .unwrap();

        assert_eq!(id, "my-sandbox");
    }

    #[test]
    fn test_get_sandbox() {
        let mut manager = SandboxManager::new();
        let id = manager.create_sandbox(None, None).unwrap();

        assert!(manager.get_sandbox(&id).is_some());
        assert!(manager.get_sandbox("non-existent").is_none());
    }

    #[test]
    fn test_delete_sandbox() {
        let mut manager = SandboxManager::new();
        let id = manager.create_sandbox(None, None).unwrap();

        assert_eq!(manager.list_sandboxes().len(), 1);

        manager.delete_sandbox(&id).unwrap();
        assert_eq!(manager.list_sandboxes().len(), 0);
    }

    #[test]
    fn test_sandbox_file_access_allowed() {
        let mut policy = SandboxPolicy::default();
        policy.file_rules = vec![FileRule::allow_read_write("/tmp"), FileRule::deny_all()];

        let mut sandbox = SandboxInstance::new("test".to_string(), policy);

        let path = std::path::Path::new("/tmp/test.txt");
        assert!(sandbox
            .check_file_access(path, FileAccessMode::Read)
            .is_ok());
        assert!(sandbox
            .check_file_access(path, FileAccessMode::ReadWrite)
            .is_ok());
    }

    #[test]
    fn test_sandbox_file_access_denied() {
        let mut policy = SandboxPolicy::default();
        policy.file_rules = vec![FileRule::deny_all()];

        let mut sandbox = SandboxInstance::new("test".to_string(), policy);

        let path = std::path::Path::new("/home/user/file.txt");
        assert!(sandbox
            .check_file_access(path, FileAccessMode::Read)
            .is_err());
    }

    #[test]
    fn test_sandbox_network_access_allowed() {
        let mut policy = SandboxPolicy::default();
        policy.network_rules = vec![NetworkRule::allow("localhost"), NetworkRule::deny_all()];

        let mut sandbox = SandboxInstance::new("test".to_string(), policy);

        assert!(sandbox
            .check_network_access("localhost", Some(8080))
            .is_ok());
    }

    #[test]
    fn test_sandbox_network_access_denied() {
        let mut policy = SandboxPolicy::default();
        policy.network_rules = vec![NetworkRule::deny_all()];

        let mut sandbox = SandboxInstance::new("test".to_string(), policy);

        assert!(sandbox
            .check_network_access("example.com", Some(80))
            .is_err());
    }

    #[test]
    fn test_audit_logging() {
        let policy = SandboxPolicy {
            name: "test".to_string(),
            enabled: true,
            file_rules: vec![FileRule::allow_read("/tmp")],
            network_rules: vec![NetworkRule::deny_all()],
            process_limits: ProcessLimits::default(),
            env_vars: std::collections::HashMap::new(),
            resource_limits: ResourceLimits::default(),
            audit_logging: true,
        };

        let mut sandbox = SandboxInstance::new("test".to_string(), policy);

        let path = std::path::Path::new("/tmp/test.txt");
        let _ = sandbox.check_file_access(path, FileAccessMode::Read);

        assert_eq!(sandbox.audit_log.len(), 1);
        assert_eq!(sandbox.audit_log[0].event_type, AuditEventType::FileAccess);
        assert_eq!(sandbox.audit_log[0].result, AuditResult::Allowed);
    }
}
