//! Unix sandbox hooks.
//!
//! Full process isolation is still a migration target. The public module is
//! present so formatting and cross-platform builds can resolve the module tree.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UnixSandboxCapability {
    PolicyOnly,
}

pub fn capability() -> UnixSandboxCapability {
    UnixSandboxCapability::PolicyOnly
}
