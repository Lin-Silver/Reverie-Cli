use crate::catalog::{Chunk, Document};
use crate::scan::{FileEntry, Result};
use crate::text::source_text;
use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::Read;
use std::path::Path;
use tree_sitter::{Language, Node, Parser, Query, QueryCursor, StreamingIterator};

const MAX_BODY_BYTES: i64 = 1024 * 1024;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
enum Syntax {
    Python,
    JavaScript,
    TypeScript,
    Tsx,
    Rust,
}

impl Syntax {
    fn from_extension(extension: &str) -> Option<Self> {
        match extension {
            "py" | "pyi" | "pyw" => Some(Self::Python),
            "js" | "mjs" | "cjs" | "jsx" => Some(Self::JavaScript),
            "ts" => Some(Self::TypeScript),
            "tsx" => Some(Self::Tsx),
            "rs" => Some(Self::Rust),
            _ => None,
        }
    }

    fn config(self) -> (Language, String) {
        let (language, tags) = match self {
            Self::Python => (tree_sitter_python::LANGUAGE, tree_sitter_python::TAGS_QUERY),
            Self::JavaScript => (
                tree_sitter_javascript::LANGUAGE,
                tree_sitter_javascript::TAGS_QUERY,
            ),
            Self::TypeScript => (
                tree_sitter_typescript::LANGUAGE_TYPESCRIPT,
                tree_sitter_typescript::TAGS_QUERY,
            ),
            Self::Tsx => (
                tree_sitter_typescript::LANGUAGE_TSX,
                tree_sitter_typescript::TAGS_QUERY,
            ),
            Self::Rust => (tree_sitter_rust::LANGUAGE, tree_sitter_rust::TAGS_QUERY),
        };
        let tags = if matches!(self, Self::TypeScript | Self::Tsx) {
            format!("{tags}\n{}", tree_sitter_javascript::TAGS_QUERY)
        } else {
            tags.to_owned()
        };
        (language.into(), tags)
    }
}

#[derive(Default)]
pub struct Parsers {
    parser: Parser,
    queries: HashMap<Syntax, (Language, Query)>,
}

impl Parsers {
    pub fn document(&mut self, root: &Path, file: FileEntry) -> Result<Document> {
        let mut document = Document {
            file,
            body: None,
            chunks: Vec::new(),
        };
        if document.file.size > MAX_BODY_BYTES {
            return Ok(document);
        }
        let path = root.join(&document.file.path);
        let source = File::open(&path)?;
        let mut bytes = Vec::with_capacity(document.file.size.try_into()?);
        source
            .take((MAX_BODY_BYTES + 1) as u64)
            .read_to_end(&mut bytes)?;
        if bytes.len() as i64 != document.file.size {
            return Err(format!("File changed while indexing: {}", path.display()).into());
        }
        let Some(body) = source_text(bytes) else {
            return Ok(document);
        };
        let extension = path
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase();
        let module = Path::new(&document.file.path)
            .with_extension("")
            .to_string_lossy()
            .replace(['/', '\\'], ".");
        if let Some(syntax) = Syntax::from_extension(&extension) {
            document.chunks = self.code(syntax, &module, &body)?;
        } else if matches!(extension.as_str(), "md" | "mdx") {
            document.chunks = headings(&module, &body);
        }
        document.body = Some(body);
        Ok(document)
    }

    fn code(&mut self, syntax: Syntax, module: &str, source: &str) -> Result<Vec<Chunk>> {
        let (language, query) = match self.queries.entry(syntax) {
            std::collections::hash_map::Entry::Occupied(entry) => entry.into_mut(),
            std::collections::hash_map::Entry::Vacant(entry) => {
                let (language, tags) = syntax.config();
                let query = Query::new(&language, &tags)?;
                entry.insert((language, query))
            }
        };
        self.parser.set_language(language)?;
        let tree = self
            .parser
            .parse(source, None)
            .ok_or("Could not parse source")?;
        let bytes = source.as_bytes();
        let mut cursor = QueryCursor::new();
        let mut results = cursor.matches(query, tree.root_node(), bytes);
        let mut seen = HashSet::new();
        let mut chunks = Vec::new();
        while let Some(found) = results.next() {
            let mut definition = None;
            let mut name = None;
            let mut docs = Vec::new();
            for capture in found.captures {
                let label = query.capture_names()[capture.index as usize];
                match label {
                    "name" => name = capture.node.utf8_text(bytes).ok(),
                    "doc" => docs.push(capture.node.utf8_text(bytes).unwrap_or_default()),
                    _ => {
                        if let Some(kind) = label.strip_prefix("definition.") {
                            definition = Some((capture.node, kind));
                        }
                    }
                }
            }
            let (Some((node, kind)), Some(name)) = (definition, name) else {
                continue;
            };
            if name.is_empty() || !seen.insert((node.start_byte(), node.end_byte(), name)) {
                continue;
            }
            let enclosing = enclosing_scope(node, bytes);
            let symbol = if enclosing.is_empty() {
                format!("{module}.{name}")
            } else {
                format!("{module}.{enclosing}.{name}")
            };
            let source = node.utf8_text(bytes)?;
            let kind = match node.kind() {
                "struct_item" | "union_item" => "STRUCT",
                "enum_item" => "ENUM",
                "trait_item" => "TRAIT",
                "type_item" => "TYPE_ALIAS",
                _ if kind == "function" && !enclosing.is_empty() && syntax == Syntax::Python => {
                    "METHOD"
                }
                _ => kind,
            };
            chunks.push(Chunk {
                name: name.to_owned(),
                symbol,
                kind: kind.to_ascii_uppercase(),
                start_line: (node.start_position().row + 1).try_into()?,
                end_line: (node.end_position().row + 1).try_into()?,
                signature: source
                    .lines()
                    .next()
                    .unwrap_or_default()
                    .chars()
                    .take(4096)
                    .collect(),
                documentation: docs.join("\n").chars().take(8192).collect(),
                body: source.chars().take(49_152).collect(),
            });
            if chunks.len() == 512 {
                break;
            }
        }
        Ok(chunks)
    }
}

fn enclosing_scope(mut node: Node<'_>, source: &[u8]) -> String {
    let mut scopes = Vec::new();
    while let Some(parent) = node.parent() {
        let field = match parent.kind() {
            "class_definition"
            | "class_declaration"
            | "mod_item"
            | "trait_item"
            | "namespace_declaration" => "name",
            "impl_item" => "type",
            _ => {
                node = parent;
                continue;
            }
        };
        if let Some(name) = parent
            .child_by_field_name(field)
            .and_then(|child| child.utf8_text(source).ok())
        {
            scopes.push(name);
        }
        node = parent;
    }
    scopes.reverse();
    scopes.join(".")
}

fn headings(module: &str, body: &str) -> Vec<Chunk> {
    let mut chunks = Vec::new();
    for (index, line) in body.lines().enumerate() {
        let line = line.trim_start();
        if !line.starts_with('#') {
            continue;
        }
        let Some(title) = line.trim_start_matches('#').strip_prefix(' ') else {
            continue;
        };
        let title = title.trim();
        if title.is_empty() {
            continue;
        }
        let line = (index + 1) as u32;
        chunks.push(Chunk {
            name: title.to_owned(),
            symbol: format!("{module}.{title}"),
            kind: "PROPERTY".into(),
            start_line: line,
            end_line: line,
            signature: title.to_owned(),
            documentation: String::new(),
            body: String::new(),
        });
        if chunks.len() == 512 {
            break;
        }
    }
    chunks
}
