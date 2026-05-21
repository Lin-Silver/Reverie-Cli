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
