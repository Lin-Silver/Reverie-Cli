use super::{Failure, refused};
use std::{
    os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle},
    time::{Duration, Instant},
};
use tokio::sync::oneshot;
use tokio_util::sync::CancellationToken;
use windows_sys::{
    Win32::{
        Foundation::{WAIT_ABANDONED, WAIT_OBJECT_0, WAIT_TIMEOUT},
        System::Threading::{CreateMutexW, ReleaseMutex, WaitForSingleObject},
    },
    w,
};

/// Hold the same logon-session mutex as the Python client through the entire async operation.
pub async fn occupy(
    cancel: &CancellationToken,
    writes: bool,
) -> Result<impl Drop + use<>, Failure> {
    let (ready, acquired) = oneshot::channel();
    let cancel = cancel.clone();
    // A Win32 mutex must be released by its acquiring thread. Dropping the returned
    // channel on any async exit wakes that thread, including when the future is dropped.
    tokio::task::spawn_blocking(move || {
        let raw = unsafe {
            CreateMutexW(
                std::ptr::null(),
                0,
                w!("Local\\ReverieDesktopOperations.v1"),
            )
        };
        let unavailable = || {
            refused(
                "DESKTOP_LOCK_FAILED",
                "Windows desktop coordination failed.",
            )
        };
        if raw.is_null() {
            let _ = ready.send(Err(unavailable()));
            return;
        }
        let mutex = unsafe { OwnedHandle::from_raw_handle(raw) };
        let deadline = Instant::now() + Duration::from_secs(60);
        loop {
            if ready.is_closed() || cancel.is_cancelled() {
                let _ = ready.send(Err(refused(
                    "CANCELLED",
                    "Cancelled before desktop dispatch.",
                )));
                return;
            }
            match unsafe { WaitForSingleObject(mutex.as_raw_handle(), 50) } {
                status @ (WAIT_OBJECT_0 | WAIT_ABANDONED) => {
                    if status == WAIT_ABANDONED && writes {
                        let _ = ready.send(Err(Failure {
                            code: "DESKTOP_OWNER_INTERRUPTED",
                            message: "Another desktop owner ended unexpectedly. Observe again before sending input.",
                            uncertain: true,
                        }));
                    } else {
                        let (release, released) = oneshot::channel::<()>();
                        if ready.send(Ok(release)).is_ok() {
                            let _ = released.blocking_recv();
                        }
                    }
                    unsafe {
                        ReleaseMutex(mutex.as_raw_handle());
                    }
                    return;
                }
                WAIT_TIMEOUT if Instant::now() < deadline => continue,
                WAIT_TIMEOUT => {
                    let _ = ready.send(Err(refused(
                        "DESKTOP_BUSY",
                        "Another Reverie operation owns the desktop.",
                    )));
                }
                _ => {
                    let _ = ready.send(Err(unavailable()));
                }
            }
            return;
        }
    });
    acquired
        .await
        .map_err(|_| refused("DESKTOP_LOCK_FAILED", "The desktop lock worker stopped."))?
}
