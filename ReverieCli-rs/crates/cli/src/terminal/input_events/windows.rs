use crossterm::event::{Event, KeyCode, KeyEvent, KeyModifiers};
use std::{
    collections::VecDeque,
    io, thread,
    time::{Duration, Instant},
};
use termwiz::input::{InputEvent, InputParser, KeyCode as NativeKey, Modifiers};
use windows_sys::Win32::System::Console::{
    ENABLE_VIRTUAL_TERMINAL_INPUT, GetConsoleMode, GetNumberOfConsoleInputEvents, GetStdHandle,
    INPUT_RECORD, KEY_EVENT, ReadConsoleInputW, STD_INPUT_HANDLE, SetConsoleMode,
};

pub struct InputEvents {
    console: usize,
    saved_mode: u32,
    parser: InputParser,
    queue: VecDeque<Event>,
    escape: Option<Instant>,
    surrogate: Option<u16>,
}

impl InputEvents {
    pub fn new() -> io::Result<Self> {
        // VT input retains the paste markers as Unicode key records. Reading
        // those records directly avoids a blocking stdin reader during shutdown.
        let console = unsafe { GetStdHandle(STD_INPUT_HANDLE) };
        let mut saved_mode = 0;
        if unsafe { GetConsoleMode(console, &mut saved_mode) } == 0
            || unsafe { SetConsoleMode(console, saved_mode | ENABLE_VIRTUAL_TERMINAL_INPUT) } == 0
        {
            return Err(io::Error::last_os_error());
        }
        Ok(Self {
            console: console as usize,
            saved_mode,
            parser: InputParser::new(),
            queue: VecDeque::new(),
            escape: None,
            surrogate: None,
        })
    }

    fn parse(&mut self, bytes: &[u8], more: bool) {
        for event in self.parser.parse_as_vec(bytes, more) {
            if let Some(event) = convert(event) {
                self.queue.push_back(event);
            }
        }
    }

    pub fn poll(&mut self, timeout: Duration) -> io::Result<Option<Event>> {
        let started = Instant::now();
        loop {
            if let Some(event) = self.queue.pop_front() {
                return Ok(Some(event));
            }
            let mut count = 0;
            if unsafe { GetNumberOfConsoleInputEvents(self.console as _, &mut count) } == 0 {
                return Err(io::Error::last_os_error());
            }
            if count > 0 {
                let mut records = [INPUT_RECORD::default(); 128];
                let mut read = 0;
                if unsafe {
                    ReadConsoleInputW(
                        self.console as _,
                        records.as_mut_ptr(),
                        count.min(128),
                        &mut read,
                    )
                } == 0
                {
                    return Err(io::Error::last_os_error());
                }
                for record in &records[..read as usize] {
                    if record.EventType != KEY_EVENT as u16 {
                        continue;
                    }
                    // KEY_EVENT selects this union member. Unicode is also
                    // delivered on Alt-code release (including surrogate pairs).
                    let key = unsafe { record.Event.KeyEvent };
                    let unit = unsafe { key.uChar.UnicodeChar };
                    if unit == 0 || (key.bKeyDown == 0 && key.wVirtualKeyCode != 18) {
                        continue;
                    }
                    if (0xd800..=0xdbff).contains(&unit) {
                        self.surrogate = Some(unit);
                        continue;
                    }
                    let text = if let Some(high) = self.surrogate.take() {
                        String::from_utf16_lossy(&[high, unit])
                    } else {
                        String::from_utf16_lossy(&[unit])
                    };
                    for _ in 0..key.wRepeatCount.max(1) {
                        self.escape = (text == "\x1b").then(Instant::now);
                        self.parse(text.as_bytes(), true);
                    }
                }
            }
            if self
                .escape
                .is_some_and(|time| time.elapsed() >= Duration::from_millis(40))
            {
                self.escape = None;
                self.parse(&[], false);
            }
            if started.elapsed() >= timeout {
                return Ok(self.queue.pop_front());
            }
            if self.queue.is_empty() {
                thread::sleep(Duration::from_millis(1));
            }
        }
    }
}

impl Drop for InputEvents {
    fn drop(&mut self) {
        unsafe { SetConsoleMode(self.console as _, self.saved_mode) };
    }
}

fn convert(event: InputEvent) -> Option<Event> {
    match event {
        InputEvent::Paste(text) => Some(Event::Paste(text)),
        InputEvent::Key(key) => {
            let mut modifiers = KeyModifiers::empty();
            for (source, target) in [
                (Modifiers::CTRL, KeyModifiers::CONTROL),
                (Modifiers::ALT, KeyModifiers::ALT),
                (Modifiers::SHIFT, KeyModifiers::SHIFT),
            ] {
                if key.modifiers.contains(source) {
                    modifiers |= target;
                }
            }
            let code = match key.key {
                NativeKey::Char('\r') | NativeKey::Enter => KeyCode::Enter,
                NativeKey::Char('\n') => {
                    modifiers |= KeyModifiers::CONTROL;
                    KeyCode::Char('j')
                }
                NativeKey::Char(ch) => KeyCode::Char(ch),
                NativeKey::Escape => KeyCode::Esc,
                NativeKey::Backspace => KeyCode::Backspace,
                NativeKey::Delete => KeyCode::Delete,
                NativeKey::Tab => KeyCode::Tab,
                NativeKey::Home | NativeKey::KeyPadHome => KeyCode::Home,
                NativeKey::End | NativeKey::KeyPadEnd => KeyCode::End,
                NativeKey::UpArrow | NativeKey::ApplicationUpArrow => KeyCode::Up,
                NativeKey::DownArrow | NativeKey::ApplicationDownArrow => KeyCode::Down,
                NativeKey::LeftArrow | NativeKey::ApplicationLeftArrow => KeyCode::Left,
                NativeKey::RightArrow | NativeKey::ApplicationRightArrow => KeyCode::Right,
                NativeKey::PageUp => KeyCode::PageUp,
                NativeKey::PageDown => KeyCode::PageDown,
                NativeKey::Function(number) => KeyCode::F(number),
                _ => return None,
            };
            Some(Event::Key(KeyEvent::new(code, modifiers)))
        }
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn vt_paste_keeps_fragmented_boundaries_newlines_and_control_text_out_of_key_actions() {
        let mut parser = InputParser::new();
        let chunks: &[&[u8]] = &[
            b"\x1b[20",
            b"0~first\r\n",
            "中文😀\x03\x1b".as_bytes(),
            b"[201",
            b"~\r",
        ];
        let events = chunks
            .iter()
            .flat_map(|bytes| parser.parse_as_vec(bytes, true))
            .filter_map(convert)
            .collect::<Vec<_>>();
        assert_eq!(
            events,
            [
                Event::Paste("first\r\n中文😀\x03".into()),
                Event::Key(KeyEvent::new(KeyCode::Enter, KeyModifiers::empty()))
            ]
        );
    }
}
