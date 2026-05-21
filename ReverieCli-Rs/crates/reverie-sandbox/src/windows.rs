//! Windows sandbox hooks.
//!
//! Full job-object isolation is still a migration target. The public module is
//! present so the crate compiles on Windows and callers can feature-detect the
//! current capability level.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WindowsSandboxCapability {
    PolicyOnly,
}

pub fn capability() -> WindowsSandboxCapability {
    WindowsSandboxCapability::PolicyOnly
}
