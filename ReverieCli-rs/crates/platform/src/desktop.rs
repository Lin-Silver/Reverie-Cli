//! Physical coordinates are bound to the DWM frame captured by Windows Graphics Capture.
mod occupation;
pub use occupation::occupy;

use serde::Serialize;
use windows_sys::Win32::{
    Foundation::{HWND, POINT, RECT},
    Graphics::Dwm::{DWMWA_EXTENDED_FRAME_BOUNDS, DwmGetWindowAttribute},
    UI::{
        HiDpi::{
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2, GetDpiForWindow,
            SetThreadDpiAwarenessContext,
        },
        Input::KeyboardAndMouse::*,
        WindowsAndMessaging::*,
    },
};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub struct Bounds {
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Window {
    handle: usize,
    pid: u32,
    pub frame: Bounds,
    dpi: u32,
    desktop: Bounds,
}

// Keep the per-monitor context on this synchronous thread only.
fn physical<T>(operation: impl FnOnce() -> Option<T>) -> Option<T> {
    let previous =
        unsafe { SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2) };
    if previous.is_null() {
        return None;
    }
    let result = operation();
    let restored = unsafe { SetThreadDpiAwarenessContext(previous) };
    if restored.is_null() {
        return None;
    }
    result
}

impl Window {
    pub fn observe(id: &str, pid: u32) -> Option<Self> {
        let handle = id.strip_prefix("w-")?.parse().ok()?;
        physical(|| Self::read(handle, pid))
    }

    fn read(handle: usize, pid: u32) -> Option<Self> {
        let hwnd = handle as HWND;
        let mut actual_pid = 0;
        let mut frame = RECT::default();
        // Read-only HWND queries; Win32 validates handles and fills the local output buffers.
        unsafe {
            if handle == 0
                || pid == 0
                || GetWindowThreadProcessId(hwnd, &mut actual_pid) == 0
                || actual_pid != pid
                || IsWindowVisible(hwnd) == 0
                || IsIconic(hwnd) != 0
                || DwmGetWindowAttribute(
                    hwnd,
                    DWMWA_EXTENDED_FRAME_BOUNDS as u32,
                    (&raw mut frame).cast(),
                    size_of::<RECT>() as u32,
                ) < 0
            {
                return None;
            }
            let dpi = GetDpiForWindow(hwnd);
            let frame = Bounds {
                x: frame.left,
                y: frame.top,
                width: frame.right.checked_sub(frame.left)?,
                height: frame.bottom.checked_sub(frame.top)?,
            };
            let desktop = Bounds {
                x: GetSystemMetrics(SM_XVIRTUALSCREEN),
                y: GetSystemMetrics(SM_YVIRTUALSCREEN),
                width: GetSystemMetrics(SM_CXVIRTUALSCREEN),
                height: GetSystemMetrics(SM_CYVIRTUALSCREEN),
            };
            if dpi == 0
                || frame.width <= 0
                || frame.height <= 0
                || desktop.width <= 0
                || desktop.height <= 0
            {
                return None;
            }
            Some(Self {
                handle,
                pid,
                frame,
                dpi,
                desktop,
            })
        }
    }
}

#[derive(Debug)]
pub struct Failure {
    pub code: &'static str,
    pub message: &'static str,
    pub uncertain: bool,
}

fn refused(code: &'static str, message: &'static str) -> Failure {
    Failure {
        code,
        message,
        uncertain: false,
    }
}

fn absolute(pixel: i32, origin: i32, size: i32) -> Option<i32> {
    let index = i64::from(pixel) - i64::from(origin);
    let size = i64::from(size);
    if !(0..size).contains(&index) || size > 65536 {
        return None;
    }
    Some(((index as u64 * 65536).div_ceil(size as u64)) as i32)
}

fn event(dx: i32, dy: i32, flags: MOUSE_EVENT_FLAGS) -> INPUT {
    INPUT {
        r#type: INPUT_MOUSE,
        Anonymous: INPUT_0 {
            mi: MOUSEINPUT {
                dx,
                dy,
                dwFlags: flags,
                ..Default::default()
            },
        },
    }
}

pub enum Gesture {
    Click { button: Button, count: u8 },
    Drag { to: (i32, i32) },
}

pub enum Button {
    Left,
    Right,
    Middle,
}

pub fn escape_down() -> bool {
    unsafe { GetAsyncKeyState(i32::from(VK_ESCAPE)) < 0 }
}

impl Window {
    /// The OS accepts one ordered input batch. Only the application can confirm the actual UI effect.
    pub fn dispatch(&self, from: (i32, i32), gesture: Gesture) -> Result<(), Failure> {
        physical(|| Some(self.dispatch_physical(from, gesture))).ok_or(Failure {
            code: "DPI_CONTEXT_FAILED",
            message: "The physical coordinate context could not be established or restored.",
            uncertain: true,
        })?
    }

    fn dispatch_physical(&self, from: (i32, i32), gesture: Gesture) -> Result<(), Failure> {
        let stale = || {
            refused(
                "STALE_IMAGE",
                "The observed window or screen geometry changed. Capture again.",
            )
        };
        if Self::read(self.handle, self.pid).as_ref() != Some(self) {
            return Err(stale());
        }
        let hwnd = self.handle as HWND;
        if unsafe { GetForegroundWindow() } != hwnd {
            return Err(refused(
                "TARGET_NOT_FOCUSED",
                "Focus the observed window and capture it again.",
            ));
        }
        let pressed = |key| unsafe { GetAsyncKeyState(i32::from(key)) } < 0;
        if escape_down() {
            return Err(refused(
                "PHYSICAL_ESCAPE",
                "Escape stopped the desktop action.",
            ));
        }
        if [
            VK_LBUTTON,
            VK_RBUTTON,
            VK_MBUTTON,
            VK_XBUTTON1,
            VK_XBUTTON2,
            VK_CONTROL,
            VK_MENU,
            VK_SHIFT,
            VK_LWIN,
            VK_RWIN,
        ]
        .into_iter()
        .any(pressed)
        {
            return Err(refused(
                "INPUT_BUSY",
                "A mouse button or modifier is already held.",
            ));
        }
        let mut gui = GUITHREADINFO {
            cbSize: size_of::<GUITHREADINFO>() as u32,
            ..Default::default()
        };
        if unsafe { GetGUIThreadInfo(0, &mut gui) } == 0 || !gui.hwndCapture.is_null() {
            return Err(refused(
                "INPUT_BUSY",
                "Mouse capture is active or its owner is unknown.",
            ));
        }
        let movement = |(x, y)| {
            if !(0..i64::from(self.frame.width)).contains(&(i64::from(x) - i64::from(self.frame.x)))
                || !(0..i64::from(self.frame.height))
                    .contains(&(i64::from(y) - i64::from(self.frame.y)))
            {
                return Err(stale());
            }
            let hit = unsafe { WindowFromPhysicalPoint(POINT { x, y }) };
            if hit.is_null() || unsafe { GetAncestor(hit, GA_ROOT) } != hwnd {
                return Err(refused(
                    "TARGET_OCCLUDED",
                    "The observed window does not receive this physical point.",
                ));
            }
            let dx = absolute(x, self.desktop.x, self.desktop.width).ok_or_else(stale)?;
            let dy = absolute(y, self.desktop.y, self.desktop.height).ok_or_else(stale)?;
            Ok(event(
                dx,
                dy,
                MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
            ))
        };
        let (down, up) = match gesture {
            Gesture::Click {
                button: Button::Right,
                ..
            } => (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
            Gesture::Click {
                button: Button::Middle,
                ..
            } => (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
            _ => (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        };
        let mut inputs = vec![movement(from)?];
        match gesture {
            Gesture::Click { count, .. } => {
                if !(1..=3).contains(&count) {
                    return Err(refused(
                        "INVALID_ARGS",
                        "Click count must be between one and three.",
                    ));
                }
                for _ in 0..count {
                    inputs.extend([event(0, 0, down), event(0, 0, up)]);
                }
            }
            Gesture::Drag { to } => {
                inputs.push(event(0, 0, down));
                let dx = i64::from(to.0) - i64::from(from.0);
                let dy = i64::from(to.1) - i64::from(from.1);
                let steps = (dx.abs().max(dy.abs()) / 8).clamp(1, 128);
                for step in 1..=steps {
                    inputs.push(movement((
                        (i64::from(from.0) + dx * step / steps) as i32,
                        (i64::from(from.1) + dy * step / steps) as i32,
                    ))?);
                }
                inputs.push(event(0, 0, up));
            }
        }
        if Self::read(self.handle, self.pid).as_ref() != Some(self)
            || unsafe { GetForegroundWindow() } != hwnd
        {
            return Err(stale());
        }
        if escape_down() {
            return Err(refused(
                "PHYSICAL_ESCAPE",
                "Escape stopped the desktop action.",
            ));
        }
        // The slice stays alive for the synchronous call. User32 retains UIPI restrictions.
        let sent = unsafe {
            SendInput(
                inputs.len() as u32,
                inputs.as_ptr(),
                size_of::<INPUT>() as i32,
            )
        } as usize;
        if sent == 0 {
            return Err(refused(
                "INPUT_REFUSED",
                "Windows did not insert any pointer input.",
            ));
        }
        if sent != inputs.len() {
            if inputs[..sent]
                .iter()
                .rev()
                .map(|i| unsafe { i.Anonymous.mi.dwFlags })
                .find(|f| *f == down || *f == up)
                == Some(down)
            {
                let release = event(0, 0, up);
                unsafe { SendInput(1, &release, size_of::<INPUT>() as i32) };
            }
            return Err(Failure {
                code: "PARTIAL_INPUT",
                message: "Windows accepted only part of the gesture. Observe before retrying.",
                uncertain: true,
            });
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn normalized_pixels_round_trip_across_virtual_displays() {
        for size in [1, 1920, 3840, 5760, 48000, 65536] {
            for pixel in 0..size {
                let normalized = absolute(pixel - 1920, -1920, size).unwrap();
                assert_eq!(
                    i64::from(normalized) * i64::from(size) / 65536,
                    i64::from(pixel)
                );
            }
            assert!(absolute(-1921, -1920, size).is_none());
            assert!(absolute(size - 1920, -1920, size).is_none());
        }
    }
}
