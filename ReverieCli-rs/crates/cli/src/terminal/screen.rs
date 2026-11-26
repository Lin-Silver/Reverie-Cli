use super::{
    Panel, PanelKind,
    connectors::{masked_input, private_command},
    cursor_backend::CursorBackend,
    input::{Input, display_text, wrapped},
};
use crossterm::{
    event::{
        DisableBracketedPaste, EnableBracketedPaste, KeyboardEnhancementFlags,
        PopKeyboardEnhancementFlags, PushKeyboardEnhancementFlags,
    },
    execute, terminal,
};
use ratatui::{
    Terminal, TerminalOptions, Viewport,
    backend::CrosstermBackend,
    layout::{Constraint, Layout},
    style::{Color, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Widget, Wrap},
};
use std::io::{self, Stdout};
use unicode_width::UnicodeWidthStr;

struct Mode {
    enhanced: bool,
}
impl Drop for Mode {
    fn drop(&mut self) {
        if self.enhanced {
            let _ = execute!(io::stdout(), PopKeyboardEnhancementFlags);
        }
        let _ = execute!(io::stdout(), DisableBracketedPaste);
        let _ = terminal::disable_raw_mode();
    }
}

pub struct Screen {
    terminal: Terminal<CursorBackend<CrosstermBackend<Stdout>>>,
    _mode: Mode,
}
impl Screen {
    pub fn new() -> io::Result<Self> {
        terminal::enable_raw_mode()?;
        let mut mode = Mode { enhanced: false };
        execute!(io::stdout(), EnableBracketedPaste)?;
        if terminal::supports_keyboard_enhancement().unwrap_or(false) {
            execute!(
                io::stdout(),
                PushKeyboardEnhancementFlags(
                    KeyboardEnhancementFlags::DISAMBIGUATE_ESCAPE_CODES
                        | KeyboardEnhancementFlags::REPORT_EVENT_TYPES
                )
            )?;
            mode.enhanced = true;
        }
        let rows = terminal::size()?.1;
        let terminal = Terminal::with_options(
            CursorBackend::new(CrosstermBackend::new(io::stdout())),
            TerminalOptions {
                viewport: Viewport::Inline(rows.saturating_sub(1).clamp(3, 12)),
            },
        )?;
        Ok(Self {
            terminal,
            _mode: mode,
        })
    }
    pub fn width(&self) -> u16 {
        terminal::size().map(|size| size.0).unwrap_or(80).max(1)
    }
    pub fn lines(&mut self, lines: &[String]) -> io::Result<()> {
        for chunk in lines.chunks(64) {
            let text = chunk.iter().cloned().map(Line::from).collect::<Vec<_>>();
            self.terminal.insert_before(chunk.len() as u16, |buffer| {
                Paragraph::new(text).render(buffer.area, buffer);
            })?;
        }
        Ok(())
    }
    pub fn print(&mut self, text: &str) -> io::Result<()> {
        self.lines(&wrapped(&display_text(text), self.width()))
    }
    pub fn feed(&mut self, pending: &mut String, text: &str) -> io::Result<()> {
        pending.push_str(text);
        let lines = wrapped(&display_text(pending), self.width());
        if lines.len() > 1 {
            self.lines(&lines[..lines.len() - 1])?;
        }
        *pending = lines.last().cloned().unwrap_or_default();
        Ok(())
    }
    pub fn flush(&mut self, pending: &mut String) -> io::Result<()> {
        if !pending.is_empty() {
            self.print(pending)?;
            pending.clear();
        }
        Ok(())
    }
    pub fn draw(
        &mut self,
        input: &Input,
        status: &str,
        live: &str,
        panel: Option<&Panel>,
    ) -> io::Result<()> {
        self.terminal.draw(|frame| {
            let hidden = panel
                .is_some_and(|panel| matches!(panel.kind, PanelKind::ConnectorSecret))
                || panel.is_none() && private_command(&input.text);
            let masked = hidden.then(|| masked_input(input));
            let input = masked.as_ref().unwrap_or(input);
            let area = frame.area();
            let input_width = area.width.saturating_sub(2).max(1);
            let input_rows = wrapped(&display_text(&input.text), input_width)
                .len()
                .clamp(1, 3) as u16
                + 2;
            let [header, body, editor, help] = Layout::vertical([
                Constraint::Length(1),
                Constraint::Min(1),
                Constraint::Length(input_rows),
                Constraint::Length(1),
            ])
            .areas(area);
            frame.render_widget(
                Paragraph::new(status).style(Style::default().fg(Color::LightMagenta)),
                header,
            );
            if let Some(panel) = panel {
                let visible = body.height.saturating_sub(1) as usize;
                let start = panel.selected.saturating_sub(visible.saturating_sub(1));
                let mut lines = vec![Line::styled(
                    display_text(&panel.title),
                    Style::default().fg(Color::LightCyan),
                )];
                for (index, label) in panel.options.iter().enumerate().skip(start).take(visible) {
                    let checked = if panel.multiple {
                        if panel.checked.contains(&index) {
                            "[x] "
                        } else {
                            "[ ] "
                        }
                    } else {
                        ""
                    };
                    lines.push(Line::from(vec![
                        Span::styled(
                            if panel.selected == index {
                                "› "
                            } else {
                                "  "
                            },
                            Style::default().fg(Color::LightMagenta),
                        ),
                        Span::raw(format!("{}{checked}{}", index + 1, display_text(label))),
                    ]));
                }
                frame.render_widget(Paragraph::new(lines), body);
            } else {
                frame.render_widget(
                    Paragraph::new(display_text(live)).wrap(Wrap { trim: false }),
                    body,
                );
            }
            let block = Block::default()
                .borders(Borders::TOP | Borders::BOTTOM)
                .title(if panel.is_some() { " Reply " } else { " You " });
            let inner = block.inner(editor);
            frame.render_widget(block, editor);
            let prefix = wrapped(&display_text(&input.text[..input.cursor]), input_width);
            let cursor_row = prefix.len().saturating_sub(1);
            let scroll = cursor_row.saturating_sub(inner.height.saturating_sub(1) as usize);
            frame.render_widget(
                Paragraph::new(display_text(&input.text))
                    .wrap(Wrap { trim: false })
                    .scroll((scroll as u16, 0)),
                inner,
            );
            let column = prefix
                .last()
                .map(|line| line.width())
                .unwrap_or(0)
                .min(inner.width.saturating_sub(1) as usize);
            if inner.width > 0 && inner.height > 0 {
                frame.set_cursor_position((
                    inner.x + column as u16,
                    inner.y + (cursor_row - scroll) as u16,
                ));
            }
            frame.render_widget(
                Paragraph::new(if hidden {
                    "Input masked · Enter submit · Esc/Ctrl+C cancel"
                } else if panel.is_some() {
                    "↑↓ select · Space multi-select · Enter submit · Esc cancel"
                } else {
                    "Enter send · Shift+Enter/Ctrl+J newline · Ctrl+C stop · /help"
                })
                .style(Style::default().fg(Color::DarkGray)),
                help,
            );
        })?;
        Ok(())
    }
}
impl Drop for Screen {
    fn drop(&mut self) {
        let _ = self.terminal.clear();
        let _ = self.terminal.show_cursor();
    }
}
