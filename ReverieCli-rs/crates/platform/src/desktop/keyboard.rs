use super::{Failure, application_escape, escape_down, refused, window_handle};
use windows_sys::Win32::{
    Foundation::HWND,
    UI::{Input::KeyboardAndMouse::*, WindowsAndMessaging::*},
};

/// An application key, or one chord with distinct modifiers. Escape uses a window message.
pub struct WindowKey {
    keys: Vec<u16>,
}

impl WindowKey {
    pub fn parse(text: &str) -> Result<Self, Failure> {
        let invalid = || refused("INVALID_ARGS", "Unsupported or reserved window shortcut.");
        let lower = text.to_ascii_lowercase();
        let mut parts = lower.split('+');
        let main = parts.next_back().ok_or_else(invalid)?;
        let mut keys = Vec::new();
        for part in parts {
            let modifier = match part {
                "ctrl" | "control" => VK_CONTROL,
                "alt" | "option" => VK_MENU,
                "shift" => VK_SHIFT,
                _ => return Err(invalid()),
            };
            if keys.contains(&modifier) {
                return Err(invalid());
            }
            keys.push(modifier);
        }
        let key = match main {
            "escape" | "esc" if keys.is_empty() => VK_ESCAPE,
            "return" | "enter" => VK_RETURN,
            "tab" => VK_TAB,
            "space" => VK_SPACE,
            "backspace" => VK_BACK,
            "delete" | "del" => VK_DELETE,
            "insert" | "ins" => VK_INSERT,
            "home" => VK_HOME,
            "end" => VK_END,
            "left" => VK_LEFT,
            "right" => VK_RIGHT,
            "up" => VK_UP,
            "down" => VK_DOWN,
            "pageup" | "page_up" | "pgup" => VK_PRIOR,
            "pagedown" | "page_down" | "pgdn" => VK_NEXT,
            s if s.len() == 1 && s.as_bytes()[0].is_ascii_alphanumeric() => {
                u16::from(s.as_bytes()[0].to_ascii_uppercase())
            }
            s => {
                let number = s.strip_prefix('f').ok_or_else(invalid)?;
                let function = number.parse::<u16>().map_err(|_| invalid())?;
                if number.starts_with('0') || !(1..=24).contains(&function) {
                    return Err(invalid());
                }
                VK_F1 + function - 1
            }
        };
        if keys.contains(&VK_MENU)
            && (matches!(key, VK_TAB | VK_F4 | VK_SPACE)
                || (keys.contains(&VK_CONTROL) && key == VK_DELETE))
        {
            return Err(invalid());
        }
        keys.push(key);
        Ok(Self { keys })
    }

    pub fn is_escape(&self) -> bool {
        self.keys == [VK_ESCAPE]
    }

    pub fn send(&self, id: &str, pid: u64) -> Result<&'static str, Failure> {
        if self.is_escape() {
            application_escape(id, pid)?;
            return Ok("window_message_queue");
        }
        let window = window_handle(id)
            .ok_or_else(|| refused("STALE_WINDOW", "Invalid window identity."))?
            as HWND;
        let mut actual_pid = 0;
        let thread = unsafe { GetWindowThreadProcessId(window, &mut actual_pid) };
        let mut gui = GUITHREADINFO {
            cbSize: size_of::<GUITHREADINFO>() as u32,
            ..Default::default()
        };
        let mut focus_pid = 0;
        let focused = || {
            refused(
                "TARGET_NOT_FOCUSED",
                "Focus the observed window before sending this shortcut.",
            )
        };
        if thread == 0
            || u64::from(actual_pid) != pid
            || unsafe { GetGUIThreadInfo(thread, &mut gui) } == 0
            || gui.hwndActive != window
            || gui.hwndFocus.is_null()
            || unsafe { GetWindowThreadProcessId(gui.hwndFocus, &mut focus_pid) } != thread
            || focus_pid != actual_pid
            || unsafe { GetAncestor(gui.hwndFocus, GA_ROOT) } != window
            || unsafe { IsWindowEnabled(window) } == 0
        {
            return Err(focused());
        }
        let held = [VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN];
        if held
            .iter()
            .chain(&self.keys)
            .any(|k| unsafe { GetAsyncKeyState(i32::from(*k)) } < 0)
        {
            return Err(refused(
                "INPUT_BUSY",
                "A modifier or requested key is already held.",
            ));
        }
        if escape_down() {
            return Err(refused(
                "PHYSICAL_ESCAPE",
                "Escape stopped the desktop action.",
            ));
        }
        let events: Vec<_> = self
            .keys
            .iter()
            .map(|&k| input(k, false))
            .chain(self.keys.iter().rev().map(|&k| input(k, true)))
            .collect();
        if unsafe { GetForegroundWindow() } != window {
            return Err(focused());
        }
        let sent = send(&events);
        if sent == 0 {
            return Err(refused(
                "INPUT_REJECTED",
                "Windows refused the foreground shortcut.",
            ));
        }
        if sent != events.len() {
            // The accepted prefix may already contain some key-ups. Release only our unmatched downs.
            let held = held_prefix(self.keys.len(), sent);
            let mut release = &events[events.len() - held..];
            while !release.is_empty() {
                let released = send(release);
                if released == 0 {
                    return Err(Failure {
                        uncertain: true,
                        ..refused(
                            "PARTIAL_INPUT",
                            "Windows refused key release after partial input. Check held keys before continuing.",
                        )
                    });
                }
                release = &release[released..];
            }
            return Err(Failure {
                uncertain: true,
                ..refused(
                    "PARTIAL_INPUT",
                    "Windows accepted part of the shortcut. Observe before retrying.",
                )
            });
        }
        Ok("foreground_input_queue")
    }
}

fn held_prefix(keys: usize, sent: usize) -> usize {
    sent.min(2 * keys - sent)
}

fn input(key: u16, up: bool) -> INPUT {
    let extended = matches!(
        key,
        VK_LEFT
            | VK_UP
            | VK_RIGHT
            | VK_DOWN
            | VK_PRIOR
            | VK_NEXT
            | VK_HOME
            | VK_END
            | VK_INSERT
            | VK_DELETE
    );
    INPUT {
        r#type: INPUT_KEYBOARD,
        Anonymous: INPUT_0 {
            ki: KEYBDINPUT {
                wVk: key,
                dwFlags: (if up { KEYEVENTF_KEYUP } else { 0 })
                    | (if extended { KEYEVENTF_EXTENDEDKEY } else { 0 }),
                ..Default::default()
            },
        },
    }
}

fn send(events: &[INPUT]) -> usize {
    unsafe {
        SendInput(
            events.len() as u32,
            events.as_ptr(),
            size_of::<INPUT>() as i32,
        ) as usize
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn window_shortcuts_reject_reserved_combinations_and_standalone_modifiers() {
        for text in [
            "Esc",
            "CTRL+a",
            "Control+Shift+Left",
            "Alt+F",
            "Page_Down",
            "F24",
        ] {
            assert!(WindowKey::parse(text).is_ok(), "{text}");
        }
        for text in [
            "Alt+Tab",
            "shift+OPTION+Tab",
            "Alt+Shift+F4",
            "Alt+Space",
            "Ctrl+Alt+Delete",
            "Ctrl+Esc",
            "Shift+Escape",
            "Win+R",
            "Meta+E",
            "Super+L",
            "Command+C",
            "Ctrl",
            "Ctrl+Ctrl+S",
            "Ctrl+",
            "F0",
            "F25",
            "Ctrl+F04",
            "",
        ] {
            assert!(WindowKey::parse(text).is_err(), "{text}");
        }
    }

    #[test]
    fn partial_shortcuts_release_exactly_the_keys_still_held() {
        for count in 1..=4 {
            let keys: Vec<_> = (0..count).collect();
            let sequence: Vec<_> = keys
                .iter()
                .map(|&k| (k, false))
                .chain(keys.iter().rev().map(|&k| (k, true)))
                .collect();
            for sent in 1..2 * count {
                let mut down = Vec::new();
                for &(key, up) in sequence[..sent]
                    .iter()
                    .chain(&sequence[2 * count - held_prefix(count, sent)..])
                {
                    if up {
                        assert_eq!(down.pop(), Some(key));
                    } else {
                        down.push(key);
                    }
                }
                assert!(down.is_empty());
            }
        }
    }
}
