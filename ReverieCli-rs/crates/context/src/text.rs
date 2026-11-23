use std::collections::HashSet;

fn starts_identifier(byte: u8) -> bool {
    byte.is_ascii_alphabetic() || byte == b'_'
}

fn is_compound(identifier: &[u8]) -> bool {
    identifier.windows(2).any(|pair| {
        ((pair[0].is_ascii_lowercase() || pair[0].is_ascii_digit()) && pair[1].is_ascii_uppercase())
            || (pair[0].is_ascii_alphabetic() && pair[1].is_ascii_digit())
    }) || identifier.windows(3).any(|triple| {
        triple[0].is_ascii_uppercase()
            && triple[1].is_ascii_uppercase()
            && triple[2].is_ascii_lowercase()
    })
}

fn split_before(identifier: &[u8], index: usize) -> bool {
    if index == 0 || index == identifier.len() {
        return false;
    }
    let previous = identifier[index - 1];
    let current = identifier[index];
    (current.is_ascii_uppercase() && (previous.is_ascii_lowercase() || previous.is_ascii_digit()))
        || (previous.is_ascii_alphabetic() && current.is_ascii_digit())
        || (previous.is_ascii_digit() && current.is_ascii_alphabetic())
        || (previous.is_ascii_uppercase()
            && current.is_ascii_uppercase()
            && identifier
                .get(index + 1)
                .is_some_and(u8::is_ascii_lowercase))
}

fn is_stopword(part: &str) -> bool {
    matches!(
        part,
        "get"
            | "set"
            | "the"
            | "and"
            | "for"
            | "not"
            | "new"
            | "add"
            | "def"
            | "cls"
            | "self"
            | "this"
            | "str"
            | "int"
            | "obj"
            | "val"
            | "var"
            | "tmp"
            | "arg"
            | "args"
            | "kwargs"
            | "return"
            | "class"
            | "true"
            | "false"
            | "none"
            | "null"
    )
}

/// Expand the same ASCII identifier vocabulary as the Python retriever.
pub fn subwords(values: &[&str], limit: usize) -> String {
    let mut seen = HashSet::new();
    let mut result = String::new();
    for text in values {
        let bytes = text.as_bytes();
        let mut next = 0;
        while next < bytes.len() {
            if !starts_identifier(bytes[next]) {
                next += 1;
                continue;
            }
            let start = next;
            next += 1;
            while next < bytes.len()
                && (starts_identifier(bytes[next]) || bytes[next].is_ascii_digit())
            {
                next += 1;
            }
            let identifier = &bytes[start..next];
            if identifier.len() < 3 || !is_compound(identifier) {
                continue;
            }
            let mut part_start = 0;
            for index in 0..=identifier.len() {
                let underscore = identifier.get(index) == Some(&b'_');
                if index != identifier.len() && !underscore && !split_before(identifier, index) {
                    continue;
                }
                if index - part_start >= 3 {
                    let part = text[start + part_start..start + index].to_ascii_lowercase();
                    if !is_stopword(&part) && !seen.contains(&part) {
                        if !result.is_empty() {
                            result.push(' ');
                        }
                        result.push_str(&part);
                        seen.insert(part);
                        if seen.len() >= limit.max(1) {
                            return result;
                        }
                    }
                }
                part_start = if underscore { index + 1 } else { index };
            }
        }
    }
    result
}

/// Match the application's source decoding and newline normalization.
pub fn source_text(bytes: Vec<u8>) -> Option<String> {
    let sample = &bytes[..bytes.len().min(8192)];
    if sample.contains(&0) {
        return None;
    }
    let non_ascii = sample
        .iter()
        .filter(|byte| !matches!(byte, b' '..=b'~' | b'\t' | b'\r' | b'\n'))
        .count();
    if non_ascii * 10 > sample.len() * 3 {
        let text = match std::str::from_utf8(sample) {
            Ok(text) => text,
            Err(error) if error.error_len().is_none() && bytes.len() >= 8192 => {
                std::str::from_utf8(&sample[..error.valid_up_to()]).ok()?
            }
            Err(_) => return None,
        };
        let controls = text
            .chars()
            .filter(|c| c.is_control() && !c.is_whitespace())
            .count();
        if controls * 10 > text.chars().count() * 3 {
            return None;
        }
    }
    let text = String::from_utf8(bytes)
        .unwrap_or_else(|error| error.into_bytes().into_iter().map(char::from).collect());
    let text = text.trim_start_matches('\u{feff}');
    if text.contains('\r') {
        Some(text.replace("\r\n", "\n").replace('\r', "\n"))
    } else {
        Some(text.to_owned())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identifier_expansion_preserves_order_limit_and_literal_underscores() {
        assert_eq!(
            subwords(
                &[
                    "getHTTPServer 中文 ModelAdmin",
                    "fooBar7Baz output_transaction"
                ],
                20
            ),
            "http server model admin foo bar baz"
        );
        assert_eq!(subwords(&["maxSpeed fastSwitch"], 2), "max speed");
    }

    #[test]
    fn source_decoding_handles_a_utf8_character_split_at_the_sample_boundary() {
        let source = format!("#{}\r\nprint('ok')", "中文".repeat(2000));
        assert_eq!(
            source_text(source.clone().into_bytes()),
            Some(source.replace("\r\n", "\n"))
        );
        assert!(source_text(vec![255; 100]).is_none());
        assert!(source_text(b"text\0png".to_vec()).is_none());
    }
}
