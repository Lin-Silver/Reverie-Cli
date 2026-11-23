use crate::catalog::{Chunk, Document, Reference};
use crate::scan::{FileEntry, Result, hash_bytes};
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
    C,
    Cpp,
    CSharp,
    Go,
    Java,
    Zig,
    Html,
    Css,
    Lua,
    GdScript,
}

impl Syntax {
    fn from_extension(extension: &str) -> Option<Self> {
        match extension {
            "py" | "pyi" | "pyw" => Some(Self::Python),
            "js" | "mjs" | "cjs" | "jsx" => Some(Self::JavaScript),
            "ts" => Some(Self::TypeScript),
            "tsx" => Some(Self::Tsx),
            "rs" => Some(Self::Rust),
            "c" | "h" => Some(Self::C),
            "cpp" | "cc" | "cxx" | "hpp" | "hh" | "hxx" => Some(Self::Cpp),
            "cs" => Some(Self::CSharp),
            "go" => Some(Self::Go),
            "java" => Some(Self::Java),
            "zig" => Some(Self::Zig),
            "html" | "htm" => Some(Self::Html),
            "css" => Some(Self::Css),
            "lua" => Some(Self::Lua),
            "gd" => Some(Self::GdScript),
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
            Self::C => (tree_sitter_c::LANGUAGE, tree_sitter_c::TAGS_QUERY),
            Self::Cpp => (tree_sitter_cpp::LANGUAGE, tree_sitter_cpp::TAGS_QUERY),
            Self::CSharp => (
                tree_sitter_c_sharp::LANGUAGE,
                tree_sitter_c_sharp::TAGS_QUERY,
            ),
            Self::Go => (tree_sitter_go::LANGUAGE, tree_sitter_go::TAGS_QUERY),
            Self::Java => (tree_sitter_java::LANGUAGE, tree_sitter_java::TAGS_QUERY),
            Self::Zig => (tree_sitter_zig::LANGUAGE, include_str!("queries/zig.scm")),
            Self::Html => (tree_sitter_html::LANGUAGE, include_str!("queries/html.scm")),
            Self::Css => (tree_sitter_css::LANGUAGE, include_str!("queries/css.scm")),
            Self::Lua => (tree_sitter_lua::LANGUAGE, tree_sitter_lua::TAGS_QUERY),
            Self::GdScript => (
                tree_sitter_gdscript::LANGUAGE,
                include_str!("queries/gdscript.scm"),
            ),
        };
        let tags = if matches!(self, Self::TypeScript | Self::Tsx) {
            format!("{tags}\n{}", tree_sitter_javascript::TAGS_QUERY)
        } else {
            let calls = if matches!(self, Self::C | Self::Cpp) {
                "\n(call_expression function: (identifier) @name) @reference.call"
            } else if self == Self::CSharp {
                "\n(invocation_expression function: (identifier) @name) @reference.call"
            } else {
                ""
            };
            format!("{tags}{calls}")
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
            references: Vec::new(),
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
        if hash_bytes(&bytes) != document.file.content_hash {
            return Err(format!("File changed while parsing: {}", path.display()).into());
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
            (document.chunks, document.references) = self.code(syntax, &module, &body)?;
        } else if matches!(extension.as_str(), "md" | "mdx") {
            document.chunks = headings(&module, &body);
        }
        let lines: Vec<&str> = body.lines().collect();
        for start in (0..lines.len()).step_by(60) {
            let end = (start + 72).min(lines.len());
            document.chunks.push(Chunk {
                name: format!("{}:{}", document.file.path, start + 1),
                symbol: format!("{module}:{}", start + 1),
                kind: "MODULE".into(),
                start_line: (start + 1) as u32,
                end_line: end as u32,
                signature: String::new(),
                documentation: String::new(),
                body: lines[start..end].join("\n"),
                language: extension.clone(),
                parent: None,
            });
        }
        document.body = Some(body);
        Ok(document)
    }

    fn code(
        &mut self,
        syntax: Syntax,
        module: &str,
        source: &str,
    ) -> Result<(Vec<Chunk>, Vec<Reference>)> {
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
        let mut root_cursor = tree.root_node().walk();
        let file_class = if syntax == Syntax::GdScript {
            tree.root_node()
                .named_children(&mut root_cursor)
                .find(|node| node.kind() == "class_name_statement")
                .and_then(|node| node.child_by_field_name("name"))
                .and_then(|node| node.utf8_text(bytes).ok())
        } else {
            None
        };
        let mut cursor = QueryCursor::new();
        let mut results = cursor.matches(query, tree.root_node(), bytes);
        let mut seen = HashSet::new();
        let mut chunks = Vec::new();
        let mut references = Vec::new();
        let mut seen_references = HashSet::new();
        while let Some(found) = results.next() {
            let mut definition = None;
            let mut name = None;
            let mut docs = Vec::new();
            let mut reference = None;
            for capture in found.captures {
                let label = query.capture_names()[capture.index as usize];
                match label {
                    "name" => name = capture.node.utf8_text(bytes).ok(),
                    "doc" => docs.push(capture.node.utf8_text(bytes).unwrap_or_default()),
                    _ => {
                        if let Some(kind) = label.strip_prefix("definition.") {
                            definition = Some((capture.node, kind));
                        }
                        if let Some(kind) = label.strip_prefix("reference.") {
                            reference = Some((capture.node, kind));
                        }
                    }
                }
            }
            if let (Some((node, kind)), Some(name)) = (reference, name) {
                let reference_node = if matches!(node.kind(), "arguments" | "argument_list") {
                    node.parent().unwrap_or(node)
                } else {
                    node
                };
                let target = reference_node
                    .child_by_field_name("function")
                    .or_else(|| reference_node.child_by_field_name("constructor"))
                    .or_else(|| {
                        (reference_node.kind() == "function_call")
                            .then(|| reference_node.child_by_field_name("name"))
                            .flatten()
                    })
                    .and_then(|function| function.utf8_text(bytes).ok())
                    .unwrap_or(name);
                let enclosing = enclosing_scope(node, bytes, file_class);
                let owner = if kind == "implementation" {
                    let implementing = reference_node
                        .child_by_field_name("type")
                        .and_then(|node| node.utf8_text(bytes).ok())
                        .unwrap_or_default();
                    [module, &enclosing, implementing]
                        .into_iter()
                        .filter(|scope| !scope.is_empty())
                        .collect::<Vec<_>>()
                        .join(".")
                } else if enclosing.is_empty() {
                    module.to_owned()
                } else {
                    format!("{module}.{enclosing}")
                };
                let line = (node.start_position().row + 1) as u32;
                if seen_references.insert((owner.clone(), target, kind, line)) {
                    references.push(Reference {
                        source: owner,
                        target: target.to_owned(),
                        kind: match kind {
                            "call" | "send" => "CALLS",
                            "implementation" => "IMPLEMENTS",
                            _ => "REFERENCES",
                        }
                        .into(),
                        line,
                    });
                }
            }
            let (Some((node, kind)), Some(name)) = (definition, name) else {
                continue;
            };
            let node = if node.kind() == "function_declarator" {
                declarator_owner(node)
            } else {
                node
            };
            let name = if syntax == Syntax::Lua && node.kind() == "function_declaration" {
                node.child_by_field_name("name")
                    .and_then(|node| node.utf8_text(bytes).ok())
                    .unwrap_or(name)
            } else {
                name
            };
            let name = if syntax == Syntax::Lua {
                name.replace(':', ".")
            } else {
                name.to_owned()
            };
            if name.is_empty()
                || chunks.len() >= 512
                || !seen.insert((node.start_byte(), node.end_byte(), name.clone()))
            {
                continue;
            }
            let enclosing = enclosing_scope(node, bytes, file_class);
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
                "struct_specifier" | "struct_declaration" => "STRUCT",
                "enum_specifier" | "enum_declaration" => "ENUM",
                "type_definition" => "TYPE_ALIAS",
                "type_spec" => match node.child_by_field_name("type").map(|node| node.kind()) {
                    Some("struct_type") => "STRUCT",
                    Some("interface_type") => "INTERFACE",
                    _ => "TYPE_ALIAS",
                },
                _ if kind == "type" => "TYPE_ALIAS",
                "variable_declaration"
                    if syntax == Syntax::Zig
                        && node
                            .children(&mut node.walk())
                            .any(|node| node.kind() == "const") =>
                {
                    "CONSTANT"
                }
                _ if kind == "function" && class_method(node) => "METHOD",
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
                documentation: documentation(node, bytes, &docs)
                    .chars()
                    .take(8192)
                    .collect(),
                body: source.chars().take(49_152).collect(),
                language: match syntax {
                    Syntax::Python => "python",
                    Syntax::JavaScript => "javascript",
                    Syntax::TypeScript | Syntax::Tsx => "typescript",
                    Syntax::Rust => "rust",
                    Syntax::C => "c",
                    Syntax::Cpp => "cpp",
                    Syntax::CSharp => "csharp",
                    Syntax::Go => "go",
                    Syntax::Java => "java",
                    Syntax::Zig => "zig",
                    Syntax::Html => "html",
                    Syntax::Css => "css",
                    Syntax::Lua => "lua",
                    Syntax::GdScript => "gdscript",
                }
                .into(),
                parent: (!enclosing.is_empty()).then(|| format!("{module}.{enclosing}")),
            });
        }
        Ok((chunks, references))
    }
}

fn documentation(node: Node<'_>, source: &[u8], captured: &[&str]) -> String {
    if !captured.is_empty() {
        return captured.join("\n");
    }
    if let Some(string) = node
        .child_by_field_name("body")
        .and_then(|body| body.named_child(0))
        .filter(|statement| statement.kind() == "expression_statement")
        .and_then(|statement| statement.named_child(0))
        .filter(|value| value.kind() == "string")
        .filter(|value| {
            !value.named_children(&mut value.walk()).any(|part| {
                part.kind() == "string_start"
                    && part
                        .utf8_text(source)
                        .unwrap_or_default()
                        .split(['\'', '"'])
                        .next()
                        .unwrap_or_default()
                        .chars()
                        .any(|ch| matches!(ch, 'f' | 'F' | 'b' | 'B'))
            })
        })
    {
        let parts = string
            .named_children(&mut string.walk())
            .filter(|part| part.kind() == "string_content")
            .filter_map(|part| part.utf8_text(source).ok())
            .collect::<Vec<_>>();
        if !parts.is_empty() {
            return parts.join("");
        }
    }
    let mut comments = Vec::new();
    let mut current = node;
    while let Some(previous) = current.prev_named_sibling() {
        if !previous.kind().contains("comment")
            || previous.end_position().row + 1 < current.start_position().row
        {
            break;
        }
        comments.push(previous.utf8_text(source).unwrap_or_default());
        current = previous;
    }
    comments.reverse();
    comments.join("\n")
}

fn class_method(mut node: Node<'_>) -> bool {
    while let Some(parent) = node.parent() {
        match parent.kind() {
            "class_definition"
            | "class_declaration"
            | "class_specifier"
            | "struct_specifier"
            | "interface_declaration" => return true,
            "function_definition"
            | "function_declaration"
            | "function_item"
            | "method_definition"
            | "method_declaration" => return false,
            _ => node = parent,
        }
    }
    false
}

fn declarator_owner(mut node: Node<'_>) -> Node<'_> {
    let original = node;
    while let Some(parent) = node.parent() {
        if matches!(
            parent.kind(),
            "function_definition" | "declaration" | "field_declaration"
        ) {
            return parent;
        }
        if matches!(parent.kind(), "parameter_declaration" | "type_definition") {
            break;
        }
        node = parent;
    }
    original
}

fn enclosing_scope(mut node: Node<'_>, source: &[u8], file_class: Option<&str>) -> String {
    let is_file_class = node.kind() == "class_name_statement";
    let mut scopes = Vec::new();
    while let Some(parent) = node.parent() {
        let field = match parent.kind() {
            "class_definition"
            | "class_declaration"
            | "function_definition"
            | "function_declaration"
            | "function_item"
            | "method_definition"
            | "method_declaration"
            | "class_specifier"
            | "struct_specifier"
            | "interface_declaration"
            | "namespace_definition"
            | "mod_item"
            | "trait_item"
            | "namespace_declaration" => "name",
            "impl_item" => "type",
            _ => {
                node = parent;
                continue;
            }
        };
        let mut named = parent.child_by_field_name(field);
        if named.is_none() && parent.kind() == "function_definition" {
            named = parent.child_by_field_name("declarator");
            while let Some(declarator) =
                named.and_then(|node| node.child_by_field_name("declarator"))
            {
                named = Some(declarator);
            }
        }
        if let Some(name) = named.and_then(|child| child.utf8_text(source).ok()) {
            scopes.push(name);
        }
        node = parent;
    }
    scopes.reverse();
    if let Some(file_class) = file_class.filter(|_| !is_file_class) {
        scopes.insert(0, file_class);
    }
    scopes.join(".").replace(':', ".").replace("..", ".")
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
            language: "markdown".into(),
            parent: None,
        });
        if chunks.len() == 512 {
            break;
        }
    }
    chunks
}
