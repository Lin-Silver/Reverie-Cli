use crate::Result;
use std::io;
use tokio::process::{Child, Command};

#[derive(Debug)]
pub struct AssignmentError(io::Error);
impl std::fmt::Display for AssignmentError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            formatter,
            "Command launched, but process-tree assignment failed; delivery is uncertain: {}",
            self.0
        )
    }
}
impl std::error::Error for AssignmentError {}

#[cfg(windows)]
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
#[cfg(windows)]
use windows_sys::Win32::{
    Foundation::HANDLE,
    System::{
        JobObjects::{
            AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
            SetInformationJobObject, TerminateJobObject,
        },
        Threading::CREATE_NO_WINDOW,
    },
};

pub struct ProcessTree {
    #[cfg(windows)]
    handle: OwnedHandle,
    #[cfg(unix)]
    group: libc::pid_t,
    active: bool,
}

impl ProcessTree {
    pub fn spawn(command: &mut Command) -> Result<(Child, Self)> {
        command.kill_on_drop(true);
        #[cfg(unix)]
        command.process_group(0);
        #[cfg(windows)]
        command.creation_flags(CREATE_NO_WINDOW);
        #[cfg(windows)]
        let handle = unsafe {
            // The unshared job handle owns all descendants of this command.
            let raw = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if raw.is_null() {
                return Err(io::Error::last_os_error().into());
            }
            let handle = OwnedHandle::from_raw_handle(raw);
            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(
                raw,
                JobObjectExtendedLimitInformation,
                &limits as *const _ as *const _,
                std::mem::size_of_val(&limits) as u32,
            ) == 0
            {
                return Err(io::Error::last_os_error().into());
            }
            handle
        };
        let child = command.spawn()?;
        #[cfg(windows)]
        unsafe {
            let process = child.raw_handle().ok_or_else(|| {
                AssignmentError(io::Error::other("Command process handle is unavailable."))
            })?;
            if AssignProcessToJobObject(handle.as_raw_handle() as HANDLE, process as HANDLE) == 0 {
                // Child::kill_on_drop terminates the parent if assignment fails.
                return Err(AssignmentError(io::Error::last_os_error()).into());
            }
        }
        let tree = Self {
            #[cfg(windows)]
            handle,
            #[cfg(unix)]
            group: child
                .id()
                .ok_or("Command process identity is unavailable.")?
                as libc::pid_t,
            active: true,
        };
        Ok((child, tree))
    }

    pub fn stop(&mut self) -> Result<()> {
        if !self.active {
            return Ok(());
        }
        #[cfg(windows)]
        let failed = unsafe { TerminateJobObject(self.handle.as_raw_handle() as HANDLE, 1) == 0 };
        #[cfg(unix)]
        let failed = unsafe { libc::kill(-self.group, libc::SIGKILL) != 0 }
            && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH);
        if failed {
            return Err(io::Error::last_os_error().into());
        }
        self.active = false;
        Ok(())
    }
}

impl Drop for ProcessTree {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}
