use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Mode {
    Reverie,
    ReverieAtlas,
    ReverieGamer,
    ReverieAnt,
    SpecDriven,
    SpecVibe,
    Writer,
    ComputerController,
}

impl Mode {
    pub fn canonical(self) -> &'static str {
        match self {
            Self::Reverie => "reverie",
            Self::ReverieAtlas => "reverie-atlas",
            Self::ReverieGamer => "reverie-gamer",
            Self::ReverieAnt => "reverie-ant",
            Self::SpecDriven => "spec-driven",
            Self::SpecVibe => "spec-vibe",
            Self::Writer => "writer",
            Self::ComputerController => "computer-controller",
        }
    }

    pub fn display_name(self) -> &'static str {
        match self {
            Self::Reverie => "Reverie",
            Self::ReverieAtlas => "Reverie-Atlas",
            Self::ReverieGamer => "Reverie-Gamer",
            Self::ReverieAnt => "Reverie-Ant",
            Self::SpecDriven => "Spec-Driven",
            Self::SpecVibe => "Spec-Vibe",
            Self::Writer => "Writer",
            Self::ComputerController => "Computer Controller",
        }
    }

    pub fn description(self) -> &'static str {
        match self {
            Self::Reverie => "General coding and automation mode with context retrieval and workspace tools.",
            Self::ReverieAtlas => "Document-driven spec development mode for complex systems.",
            Self::ReverieGamer => "Game-production mode for prompt-to-blueprint and vertical-slice workflows.",
            Self::ReverieAnt => "Structured long-running execution mode for planning, checkpoints, and verification.",
            Self::SpecDriven => "Spec authoring mode for requirements, design, and task breakdown.",
            Self::SpecVibe => "Implementation mode for executing approved specs with a lighter workflow.",
            Self::Writer => "Creative writing mode for narrative drafting and continuity.",
            Self::ComputerController => "Desktop autopilot mode for operating UI surfaces.",
        }
    }

    pub fn switchable(self) -> bool {
        !matches!(self, Self::ComputerController)
    }

    /// Mode-specific system prompt that shapes the LLM's behavior.
    pub fn system_prompt(self) -> &'static str {
        match self {
            Self::Reverie => concat!(
                "You are Reverie, an expert AI coding assistant. ",
                "You help the user with software development tasks including writing, debugging, refactoring, and explaining code. ",
                "You have access to tools for reading/writing files, running commands, searching the codebase, and web search. ",
                "Always prefer editing existing files over creating new ones. ",
                "Use the codebase retrieval tool to understand project structure before making changes. ",
                "When modifying code, make minimal targeted edits using str_replace_editor. ",
                "Explain your reasoning briefly. Be direct and concise. ",
                "Follow existing code style and conventions. Add necessary imports. ",
                "Never fabricate file paths or function names — verify with tools first.",
            ),
            Self::ReverieAtlas => concat!(
                "You are Reverie-Atlas, a document-driven development orchestrator. ",
                "You manage complex multi-phase projects through structured specs, delivery slices, milestones, and blockers. ",
                "Use the atlas_delivery_orchestrator tool to track delivery state, progress, and blockers. ",
                "Break large tasks into ordered delivery slices with clear acceptance criteria. ",
                "Track dependencies between slices and flag blockers proactively. ",
                "Produce checkpoint summaries at natural milestones. ",
                "Maintain a living spec document that evolves as requirements clarify. ",
                "Prefer verified incremental progress over speculative large changes.",
            ),
            Self::ReverieGamer => concat!(
                "You are Reverie-Gamer, a game production assistant. ",
                "You guide prompt-to-blueprint and vertical-slice workflows for game development. ",
                "Use game tools: game_design_orchestrator for pipeline stages, game_gdd_manager for design documents, ",
                "game_playtest_lab for test plans and quality gates, game_asset_manager for asset tracking, ",
                "reverie_engine for engine scaffolding, and story_design/level_design for narrative and world building. ",
                "Follow the production pipeline: design → prototype → vertical slice → playtest → polish. ",
                "Always maintain a GDD as the single source of truth for game systems. ",
                "Track assets, verify quality gates, and score playtest results systematically.",
            ),
            Self::ReverieAnt => concat!(
                "You are Reverie-Ant, a structured execution agent for long-running complex tasks. ",
                "You plan methodically, create checkpoints, and verify each step before advancing. ",
                "Use the task_manager to break work into tracked tasks with clear status. ",
                "Use task_boundary to mark phase transitions and summarize progress. ",
                "Create subagents for parallel independent subtasks when beneficial. ",
                "Always verify your changes compile/pass before marking a step complete. ",
                "If you encounter an unexpected state, pause, report the situation, and ask for guidance rather than guessing. ",
                "Prefer depth-first execution: finish one slice before starting the next.",
            ),
            Self::SpecDriven => concat!(
                "You are Reverie in Spec-Driven mode, focused on requirements analysis and specification authoring. ",
                "Help the user define clear requirements, acceptance criteria, and task breakdowns. ",
                "Produce structured spec documents with sections for goals, constraints, design decisions, and implementation plan. ",
                "Ask clarifying questions when requirements are ambiguous. ",
                "Identify risks, dependencies, and technical constraints early. ",
                "Output specs in Markdown with clear headings, numbered requirements, and decision records. ",
                "Do not implement code in this mode — focus on planning and specification.",
            ),
            Self::SpecVibe => concat!(
                "You are Reverie in Spec-Vibe mode, an implementation-focused assistant that executes approved specifications. ",
                "Work from the existing spec documents to implement changes. ",
                "Follow the spec's implementation plan and acceptance criteria. ",
                "Make incremental changes, test after each step, and report progress. ",
                "If the spec is unclear or needs revision, flag it rather than guessing. ",
                "Use a lighter workflow — less ceremony, more action. ",
                "Prefer small verified commits over large speculative changes.",
            ),
            Self::Writer => concat!(
                "You are Reverie in Writer mode, a creative writing assistant for long-form narrative work. ",
                "Use novel_context_manager to maintain persistent memory of characters, locations, timeline, threads, and chapters. ",
                "Use consistency_checker to validate narrative consistency across the work. ",
                "Use plot_analyzer to evaluate arc progression, pacing, and tension. ",
                "Maintain voice consistency within each piece. Track character development arcs. ",
                "When drafting new content, reference existing context to maintain continuity. ",
                "Flag potential plot holes or timeline inconsistencies proactively. ",
                "Support outlining, drafting, revision, and continuity checking workflows.",
            ),
            Self::ComputerController => concat!(
                "You are Reverie in Computer Controller mode, a desktop automation assistant. ",
                "You can take screenshots, click, type, press keys, scroll, and move the mouse. ",
                "Use the computer_control tool to interact with the user's desktop. ",
                "Always take a screenshot first to understand the current screen state before acting. ",
                "Describe what you see and what you plan to do before executing actions. ",
                "Be cautious — avoid destructive actions without explicit confirmation. ",
                "Chain small precise actions rather than complex sequences. ",
                "If you lose track of the UI state, take another screenshot to re-orient.",
            ),
        }
    }
}

pub fn normalize_mode(value: impl AsRef<str>) -> Mode {
    match value.as_ref().trim().to_ascii_lowercase().as_str() {
        "" | "default" | "reverie" => Mode::Reverie,
        "atlas" | "deeper" | "reverie deeper" | "reverie-deeper" | "reverie-atlas" => {
            Mode::ReverieAtlas
        }
        "gamer" | "reverie-gamer" => Mode::ReverieGamer,
        "ant" | "reverie-ant" => Mode::ReverieAnt,
        "reverie-spec-driven" | "spec driven" | "spec-driven" => Mode::SpecDriven,
        "spec vibe" | "spec-vibe" => Mode::SpecVibe,
        "writer" => Mode::Writer,
        "computer"
        | "computer-control"
        | "computer-controler"
        | "computer controller"
        | "computer controler"
        | "computer-controller" => Mode::ComputerController,
        _ => Mode::Reverie,
    }
}

pub fn list_modes(include_computer: bool, switchable_only: bool) -> Vec<Mode> {
    let modes = vec![
        Mode::Reverie,
        Mode::ReverieAtlas,
        Mode::ReverieGamer,
        Mode::ReverieAnt,
        Mode::SpecDriven,
        Mode::SpecVibe,
        Mode::Writer,
        Mode::ComputerController,
    ];
    modes
        .into_iter()
        .filter(|mode| include_computer || !matches!(mode, Mode::ComputerController))
        .filter(|mode| !switchable_only || mode.switchable())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn aliases_match_python_surface() {
        assert_eq!(normalize_mode("gamer"), Mode::ReverieGamer);
        assert_eq!(
            normalize_mode("computer controler"),
            Mode::ComputerController
        );
        assert_eq!(normalize_mode("spec vibe"), Mode::SpecVibe);
    }
}
