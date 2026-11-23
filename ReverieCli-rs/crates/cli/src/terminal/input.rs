use unicode_segmentation::UnicodeSegmentation;
use unicode_width::UnicodeWidthStr;

#[derive(Clone, Default)]
pub struct Input {
    pub text: String,
    pub cursor: usize,
}

impl Input {
    pub fn insert(&mut self, text: &str) {
        self.text.insert_str(self.cursor, text);
        self.cursor += text.len();
    }
    pub fn left(&mut self) {
        self.cursor = self.text[..self.cursor]
            .grapheme_indices(true)
            .next_back()
            .map(|(i, _)| i)
            .unwrap_or(0);
    }
    pub fn right(&mut self) {
        if let Some(grapheme) = self.text[self.cursor..].graphemes(true).next() {
            self.cursor += grapheme.len();
        }
    }
    pub fn backspace(&mut self) {
        let end = self.cursor;
        self.left();
        self.text.replace_range(self.cursor..end, "");
    }
    pub fn delete(&mut self) {
        let start = self.cursor;
        self.right();
        self.text.replace_range(start..self.cursor, "");
        self.cursor = start;
    }
    pub fn home(&mut self) {
        self.cursor = self.text[..self.cursor]
            .rfind('\n')
            .map(|i| i + 1)
            .unwrap_or(0);
    }
    pub fn end(&mut self) {
        self.cursor += self.text[self.cursor..]
            .find('\n')
            .unwrap_or(self.text.len() - self.cursor);
    }
    pub fn vertical(&mut self, up: bool) {
        let line_start = self.text[..self.cursor]
            .rfind('\n')
            .map(|i| i + 1)
            .unwrap_or(0);
        let column = self.text[line_start..self.cursor].width();
        let target = if up {
            if line_start == 0 {
                return;
            }
            self.text[..line_start - 1]
                .rfind('\n')
                .map(|i| i + 1)
                .unwrap_or(0)
        } else {
            let Some(end) = self.text[self.cursor..].find('\n') else {
                return;
            };
            self.cursor + end + 1
        };
        let mut width = 0;
        self.cursor = target;
        for grapheme in self.text[target..]
            .split('\n')
            .next()
            .unwrap_or_default()
            .graphemes(true)
        {
            if width + grapheme.width() > column {
                break;
            }
            width += grapheme.width();
            self.cursor += grapheme.len();
        }
    }
    pub fn take(&mut self) -> String {
        self.cursor = 0;
        std::mem::take(&mut self.text)
    }
}

pub fn display_text(text: &str) -> String {
    text.chars()
        .filter(|ch| !ch.is_control() || *ch == '\n' || *ch == '\t')
        .collect::<String>()
        .replace('\t', "    ")
}

pub fn wrapped(text: &str, width: u16) -> Vec<String> {
    let mut lines = Vec::new();
    let mut line = String::new();
    let mut column = 0;
    for grapheme in text.graphemes(true) {
        if grapheme == "\n" {
            lines.push(std::mem::take(&mut line));
            column = 0;
        } else {
            let size = grapheme.width();
            if column > 0 && column + size > usize::from(width.max(1)) {
                lines.push(std::mem::take(&mut line));
                column = 0;
            }
            line.push_str(grapheme);
            column += size;
        }
    }
    lines.push(line);
    lines
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn editing_and_wrapping_keep_cjk_combining_and_emoji_graphemes_intact() {
        let mut input = Input::default();
        input.insert("中文e\u{301}👩‍💻\n第二行");
        input.home();
        input.left();
        input.backspace();
        assert_eq!(input.text, "中文e\u{301}\n第二行");
        input.backspace();
        assert_eq!(input.text, "中文\n第二行");
        input.home();
        input.right();
        input.vertical(false);
        assert_eq!(&input.text[..input.cursor], "中文\n第");
        input.delete();
        assert_eq!(input.text, "中文\n第行");
        assert_eq!(wrapped("中👩‍💻文", 4), ["中👩‍💻", "文"]);
        assert_eq!(wrapped("a\n\nlast", 80), ["a", "", "last"]);
        assert_eq!(display_text("a\u{1b}[31mb\t\nc"), "a[31mb    \nc");
    }
}
