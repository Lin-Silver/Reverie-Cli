use crate::modes::{list_modes, normalize_mode, Mode};
use reverie_tools::ToolRegistry;
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct CommandSpec {
    pub name: &'static str,
    pub aliases: &'static [&'static str],
    pub description: &'static str,
    pub category: &'static str,
}

pub const COMMANDS: &[CommandSpec] = &[
    CommandSpec {
        name: "help",
        aliases: &[],
        description: "Browse the live command catalog.",
        category: "core",
    },
    CommandSpec {
        name: "status",
        aliases: &[],
        description: "Show active model, source, session, and health.",
        category: "core",
    },
    CommandSpec {
        name: "doctor",
        aliases: &["harness"],
        description: "Audit workspace harness and verification posture.",
        category: "core",
    },
    CommandSpec {
        name: "model",
        aliases: &[],
        description: "Manage standard model presets.",
        category: "model",
    },
    CommandSpec {
        name: "mode",
        aliases: &[],
        description: "Show or switch operating modes.",
        category: "mode",
    },
    CommandSpec {
        name: "codex",
        aliases: &[],
        description: "Activate Codex and choose model or reasoning.",
        category: "provider",
    },
    CommandSpec {
        name: "nvidia",
        aliases: &[],
        description: "Activate NVIDIA and choose model or reasoning.",
        category: "provider",
    },
    CommandSpec {
        name: "modelscope",
        aliases: &[],
        description: "Activate ModelScope models.",
        category: "provider",
    },
    CommandSpec {
        name: "geminicli",
        aliases: &[],
        description: "Configure Gemini CLI integration.",
        category: "provider",
    },
    CommandSpec {
        name: "search",
        aliases: &[],
        description: "Run a web search.",
        category: "tools",
    },
    CommandSpec {
        name: "index",
        aliases: &[],
        description: "Rebuild the workspace index.",
        category: "context",
    },
    CommandSpec {
        name: "tools",
        aliases: &[],
        description: "List tools visible to the active model and mode.",
        category: "tools",
    },
    CommandSpec {
        name: "skills",
        aliases: &[],
        description: "Inspect discovered SKILL.md instructions.",
        category: "tools",
    },
    CommandSpec {
        name: "plugins",
        aliases: &[],
        description: "Manage runtime plugins.",
        category: "plugins",
    },
    CommandSpec {
        name: "mcp",
        aliases: &[],
        description: "Manage MCP servers and resources.",
        category: "plugins",
    },
    CommandSpec {
        name: "setting",
        aliases: &["settings"],
        description: "View or change workspace settings.",
        category: "settings",
    },
    CommandSpec {
        name: "workspace",
        aliases: &[],
        description: "Manage workspace-local configuration.",
        category: "settings",
    },
    CommandSpec {
        name: "sessions",
        aliases: &[],
        description: "Browse sessions.",
        category: "session",
    },
    CommandSpec {
        name: "rollback",
        aliases: &["undo", "redo", "checkpoints", "operations"],
        description: "Restore checkpoints and inspect operation history.",
        category: "session",
    },
    CommandSpec {
        name: "gdd",
        aliases: &[],
        description: "Manage game design documents.",
        category: "gamer",
    },
    CommandSpec {
        name: "assets",
        aliases: &[],
        description: "Manage game assets.",
        category: "gamer",
    },
    CommandSpec {
        name: "blueprint",
        aliases: &["bp"],
        description: "Compile or inspect game blueprints.",
        category: "gamer",
    },
    CommandSpec {
        name: "scaffold",
        aliases: &[],
        description: "Create runtime project foundations.",
        category: "gamer",
    },
    CommandSpec {
        name: "engine",
        aliases: &[],
        description: "Create and validate Reverie Engine projects.",
        category: "gamer",
    },
    CommandSpec {
        name: "modeling",
        aliases: &["blender"],
        description: "Run modeling and Blender workflows.",
        category: "gamer",
    },
    CommandSpec {
        name: "playtest",
        aliases: &["pt"],
        description: "Run playtest and quality-gate workflows.",
        category: "gamer",
    },
    CommandSpec {
        name: "CE",
        aliases: &[],
        description: "Inspect and manage Context Engine state.",
        category: "context",
    },
];

pub fn command_catalog() -> &'static [CommandSpec] {
    COMMANDS
}

pub fn resolve_command(name: &str) -> Option<&'static CommandSpec> {
    let query = name.trim();
    COMMANDS.iter().find(|cmd| {
        cmd.name.eq_ignore_ascii_case(query)
            || cmd.aliases.iter().any(|a| a.eq_ignore_ascii_case(query))
    })
}

pub fn render_help() -> String {
    let mut lines = Vec::new();
    for command in COMMANDS {
        let alias = if command.aliases.is_empty() {
            String::new()
        } else {
            format!(" ({})", command.aliases.join(", "))
        };
        lines.push(format!(
            "/{}{} - {}",
            command.name, alias, command.description
        ));
    }
    lines.join("\n")
}

pub fn render_mode_list(current: Mode) -> String {
    list_modes(true, false)
        .into_iter()
        .map(|mode| {
            let marker = if mode == current { "*" } else { " " };
            format!("{marker} {} - {}", mode.canonical(), mode.description())
        })
        .collect::<Vec<_>>()
        .join("\n")
}

pub fn render_tool_list(mode: Mode) -> String {
    ToolRegistry::builtin()
        .visible_for_mode(mode.canonical())
        .into_iter()
        .map(|tool| format!("{} - {}", tool.name, tool.description))
        .collect::<Vec<_>>()
        .join("\n")
}

pub fn command_to_mode_hint(command: &str) -> Option<Mode> {
    match command.trim().to_ascii_lowercase().as_str() {
        "gdd" | "assets" | "blueprint" | "bp" | "scaffold" | "engine" | "modeling" | "blender"
        | "playtest" | "pt" => Some(Mode::ReverieGamer),
        "ce" | "index" => Some(Mode::Reverie),
        other => {
            let mode = normalize_mode(other);
            (mode != Mode::Reverie || other == "reverie").then_some(mode)
        }
    }
}
