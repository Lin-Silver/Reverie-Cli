//! Skill executor for running skills in the context of a project.

use crate::loader::SkillLoader;
use crate::types::*;
use anyhow::{anyhow, Result};
use tracing::{debug, info, warn};

/// Skill executor
pub struct SkillExecutor {
    /// Skill loader
    loader: SkillLoader,
}

impl SkillExecutor {
    /// Create a new skill executor
    pub fn new(loader: SkillLoader) -> Self {
        Self { loader }
    }

    /// Execute a skill by name
    pub async fn execute(
        &self,
        name: &str,
        context: SkillInvocationContext,
    ) -> Result<SkillExecutionResult> {
        let skill = self
            .loader
            .get(name)
            .await
            .ok_or_else(|| anyhow!("Skill not found: {}", name))?;

        info!("Executing skill: {}", name);

        let instructions = parse_skill_instructions(&skill.content)?;
        let result = self.run_skill(&skill, &instructions, context).await?;

        Ok(result)
    }

    /// Run a skill with parsed instructions
    async fn run_skill(
        &self,
        skill: &Skill,
        instructions: &[SkillStep],
        context: SkillInvocationContext,
    ) -> Result<SkillExecutionResult> {
        let mut output = String::new();
        let mut errors = Vec::new();

        for (i, step) in instructions.iter().enumerate() {
            debug!(
                "Executing step {}/{}: {}",
                i + 1,
                instructions.len(),
                step.description
            );

            match self.execute_step(step, &context).await {
                Ok(step_output) => {
                    output.push_str(&format!("Step {}: {}\n", i + 1, step.description));
                    output.push_str(&step_output);
                    output.push('\n');
                }
                Err(e) => {
                    errors.push(format!("Step {}: {}", i + 1, e));
                    warn!("Step failed: {}", e);
                }
            }
        }

        Ok(SkillExecutionResult {
            skill_name: skill.name.clone(),
            success: errors.is_empty(),
            output,
            errors,
        })
    }

    /// Execute a single skill step
    async fn execute_step(
        &self,
        step: &SkillStep,
        _context: &SkillInvocationContext,
    ) -> Result<String> {
        Ok(format!("Executed: {}", step.description))
    }

    /// List all available skills
    pub async fn list_skills(&self) -> Vec<Skill> {
        self.loader.list_all().await
    }

    /// Search skills
    pub async fn search_skills(&self, pattern: &str) -> Vec<Skill> {
        self.loader.search(pattern).await
    }
}

/// A step in a skill
#[derive(Debug, Clone)]
pub struct SkillStep {
    /// Step number
    pub number: usize,
    /// Step description/instruction
    pub description: String,
    /// Optional command to execute
    pub command: Option<String>,
    /// Optional file to read
    pub read_file: Option<String>,
    /// Optional file to write
    pub write_file: Option<String>,
}

/// Result of skill execution
#[derive(Debug, Clone)]
pub struct SkillExecutionResult {
    /// Name of the executed skill
    pub skill_name: String,
    /// Whether execution succeeded
    pub success: bool,
    /// Execution output
    pub output: String,
    /// Errors encountered
    pub errors: Vec<String>,
}

/// Parse skill content into structured steps
fn parse_skill_instructions(content: &str) -> Result<Vec<SkillStep>> {
    let mut steps = Vec::new();
    let mut current_step = 0;
    let mut current_desc = String::new();

    for line in content.lines() {
        let trimmed = line.trim();

        if let Some(num) = trimmed.strip_prefix(|c: char| c.is_ascii_digit()) {
            if let Some(step_num) = num.trim_start().chars().next().and_then(|c| c.to_digit(10)) {
                if !current_desc.is_empty() {
                    steps.push(SkillStep {
                        number: current_step,
                        description: current_desc.trim().to_string(),
                        command: None,
                        read_file: None,
                        write_file: None,
                    });
                }
                current_step = step_num as usize;
                current_desc = trimmed[trimmed.find(|c: char| !c.is_ascii_digit()).unwrap_or(0)..]
                    .trim()
                    .to_string();
                continue;
            }
        }

        if !trimmed.is_empty() && !trimmed.starts_with('#') {
            if current_desc.is_empty() {
                current_desc = trimmed.to_string();
            } else {
                current_desc.push('\n');
                current_desc.push_str(trimmed);
            }
        }
    }

    if !current_desc.is_empty() {
        steps.push(SkillStep {
            number: current_step,
            description: current_desc.trim().to_string(),
            command: None,
            read_file: None,
            write_file: None,
        });
    }

    Ok(steps)
}
