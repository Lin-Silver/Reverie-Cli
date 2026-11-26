use crate::Result;

pub const MESSAGE_LIMIT: usize = 16 * 1024 * 1024;

#[derive(Default)]
pub struct Event {
    pub kind: String,
    pub data: String,
    pub id: Option<String>,
}

#[derive(Default)]
pub struct Decoder {
    bytes: Vec<u8>,
    event: Event,
}

impl Decoder {
    pub fn push(&mut self, bytes: &[u8]) -> Result<Vec<Event>> {
        self.bytes.extend_from_slice(bytes);
        if self.bytes.len() + self.event.data.len() > MESSAGE_LIMIT {
            return Err("MCP event exceeds 16 MiB.".into());
        }
        let mut events = Vec::new();
        let mut consumed = 0;
        while let Some(relative) = self.bytes[consumed..]
            .iter()
            .position(|byte| matches!(byte, b'\r' | b'\n'))
        {
            let end = consumed + relative;
            if self.bytes[end] == b'\r' && end + 1 == self.bytes.len() {
                break;
            }
            let line = std::str::from_utf8(&self.bytes[consumed..end])?;
            consumed = end + 1;
            if self.bytes[end] == b'\r' && self.bytes.get(consumed) == Some(&b'\n') {
                consumed += 1;
            }
            if line.is_empty() {
                if !self.event.data.is_empty() {
                    self.event.data.pop();
                    events.push(std::mem::take(&mut self.event));
                } else {
                    self.event.kind.clear();
                }
                continue;
            }
            if line.starts_with(':') {
                continue;
            }
            let (field, value) = line.split_once(':').unwrap_or((line, ""));
            let value = value.strip_prefix(' ').unwrap_or(value);
            match field {
                "event" => self.event.kind = value.into(),
                "data" => {
                    self.event.data.push_str(value);
                    self.event.data.push('\n');
                }
                "id" if !value.contains('\0') => self.event.id = Some(value.into()),
                _ => {}
            }
        }
        self.bytes.drain(..consumed);
        Ok(events)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn split_utf8_crlf_comments_and_multiline_events_are_preserved() {
        let wire =
            ":keepalive\r\nevent: message\r\nid: 7\r\ndata: 中文\r\ndata: next\r\n\r\n".as_bytes();
        let mut decoder = Decoder::default();
        let mut messages = Vec::new();
        for chunk in wire.chunks(1) {
            messages.extend(decoder.push(chunk).unwrap());
        }
        assert_eq!(messages.len(), 1);
        assert_eq!(messages[0].data, "中文\nnext");
        assert_eq!(messages[0].kind, "message");
        assert_eq!(messages[0].id.as_deref(), Some("7"));
    }
}
