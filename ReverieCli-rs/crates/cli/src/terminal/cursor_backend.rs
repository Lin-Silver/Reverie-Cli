use ratatui::{
    backend::{Backend, ClearType, WindowSize},
    buffer::Cell,
    layout::{Position, Size},
};
use unicode_width::UnicodeWidthStr;

/// Raw mode disables input echo, so this renderer owns all cursor movements.
/// Query the terminal once, then track writes without injecting CPR into pasted input.
pub(super) struct CursorBackend<B> {
    inner: B,
    cursor: Option<Position>,
}
impl<B> CursorBackend<B> {
    pub fn new(inner: B) -> Self {
        Self {
            inner,
            cursor: None,
        }
    }
}
impl<B: Backend> Backend for CursorBackend<B> {
    type Error = B::Error;
    fn draw<'a, I>(&mut self, content: I) -> Result<(), Self::Error>
    where
        I: Iterator<Item = (u16, u16, &'a Cell)>,
    {
        let size = self.inner.size()?;
        let mut final_position = None;
        // Inline insertions include the empty cells covered by wide glyphs.
        // Writing those cells would add spaces after CJK and emoji in scrollback.
        let mut covered = None;
        let visible = content.filter(|(x, y, cell)| {
            if covered.is_some_and(|(row, end)| row == *y && *x < end) {
                return false;
            }
            let width = cell.symbol().width() as u16;
            covered = (width > 1).then_some((*y, x.saturating_add(width)));
            true
        });
        self.inner.draw(visible.inspect(|(x, y, cell)| {
            final_position = Some(Position {
                x: x.saturating_add(cell.symbol().width() as u16)
                    .min(size.width.saturating_sub(1)),
                y: *y,
            });
        }))?;
        if let Some(position) = final_position {
            self.cursor = Some(position);
        }
        Ok(())
    }
    fn append_lines(&mut self, n: u16) -> Result<(), Self::Error> {
        let size = self.inner.size()?;
        self.inner.append_lines(n)?;
        if let Some(cursor) = &mut self.cursor {
            cursor.y = cursor
                .y
                .saturating_add(n)
                .min(size.height.saturating_sub(1));
        }
        Ok(())
    }
    fn hide_cursor(&mut self) -> Result<(), Self::Error> {
        self.inner.hide_cursor()
    }
    fn show_cursor(&mut self) -> Result<(), Self::Error> {
        self.inner.show_cursor()
    }
    fn get_cursor_position(&mut self) -> Result<Position, Self::Error> {
        let size = self.inner.size()?;
        let cursor = match self.cursor {
            Some(cursor) => cursor,
            None => self.inner.get_cursor_position()?,
        };
        let cursor = Position {
            x: cursor.x.min(size.width.saturating_sub(1)),
            y: cursor.y.min(size.height.saturating_sub(1)),
        };
        self.cursor = Some(cursor);
        Ok(cursor)
    }
    fn set_cursor_position<P: Into<Position>>(&mut self, position: P) -> Result<(), Self::Error> {
        let size = self.inner.size()?;
        let position = position.into();
        let position = Position {
            x: position.x.min(size.width.saturating_sub(1)),
            y: position.y.min(size.height.saturating_sub(1)),
        };
        self.inner.set_cursor_position(position)?;
        self.cursor = Some(position);
        Ok(())
    }
    fn clear(&mut self) -> Result<(), Self::Error> {
        self.inner.clear()
    }
    fn clear_region(&mut self, clear_type: ClearType) -> Result<(), Self::Error> {
        self.inner.clear_region(clear_type)
    }
    fn size(&self) -> Result<Size, Self::Error> {
        self.inner.size()
    }
    fn window_size(&mut self) -> Result<WindowSize, Self::Error> {
        self.inner.window_size()
    }
    fn flush(&mut self) -> Result<(), Self::Error> {
        self.inner.flush()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::{
        Terminal, TerminalOptions, Viewport,
        backend::TestBackend,
        widgets::{Paragraph, Widget},
    };
    #[test]
    fn renderer_tracks_unicode_explicit_positions_scroll_and_resize_without_more_queries() {
        let mut backend = CursorBackend::new(TestBackend::new(20, 10));
        backend.inner.set_cursor_position((2, 3)).unwrap();
        assert_eq!(backend.get_cursor_position().unwrap(), Position::new(2, 3));
        backend.inner.set_cursor_position((19, 9)).unwrap();
        assert_eq!(backend.get_cursor_position().unwrap(), Position::new(2, 3));
        backend
            .draw(std::iter::once((4, 5, &Cell::new("中"))))
            .unwrap();
        assert_eq!(backend.get_cursor_position().unwrap(), Position::new(6, 5));
        backend.append_lines(20).unwrap();
        assert_eq!(backend.get_cursor_position().unwrap(), Position::new(6, 9));
        backend.set_cursor_position((18, 7)).unwrap();
        backend.inner.resize(8, 4);
        assert_eq!(backend.get_cursor_position().unwrap(), Position::new(7, 3));
    }
    #[test]
    fn actual_inline_render_and_insert_use_the_owned_cursor() {
        let backend = CursorBackend::new(TestBackend::new(40, 20));
        let mut terminal = Terminal::with_options(
            backend,
            TerminalOptions {
                viewport: Viewport::Inline(8),
            },
        )
        .unwrap();
        terminal
            .draw(|frame| {
                frame.render_widget(Paragraph::new("Draft 中文😀"), frame.area());
                frame.set_cursor_position((4, 6));
            })
            .unwrap();
        terminal
            .backend_mut()
            .inner
            .set_cursor_position((39, 19))
            .unwrap();
        terminal
            .insert_before(2, |buffer| {
                Paragraph::new("Reply\nOriginal text").render(buffer.area, buffer)
            })
            .unwrap();
        assert_eq!(
            terminal.get_cursor_position().unwrap(),
            Position::new(39, 1)
        );
        terminal
            .draw(|frame| {
                frame.render_widget(Paragraph::new("Draft 中文😀"), frame.area());
                frame.set_cursor_position((4, 8));
            })
            .unwrap();
        assert_eq!(terminal.get_cursor_position().unwrap(), Position::new(4, 8));
    }
}
