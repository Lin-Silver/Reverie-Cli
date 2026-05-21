//! In-process subagent registry.

use crate::types::{
    SubagentConfig, SubagentDefinition, SubagentRun, SubagentSpawnRequest, SubagentSpawnResult,
    SubagentStatus,
};
use anyhow::{anyhow, Result};
use chrono::Utc;
use std::collections::HashMap;

#[derive(Debug, Clone)]
pub struct SubagentManager {
    config: SubagentConfig,
    definitions: HashMap<String, SubagentDefinition>,
    runs: HashMap<String, SubagentRun>,
    next_id: u64,
}

impl SubagentManager {
    pub fn new(config: SubagentConfig) -> Self {
        Self {
            config,
            definitions: HashMap::new(),
            runs: HashMap::new(),
            next_id: 1,
        }
    }

    pub fn register(&mut self, definition: SubagentDefinition) -> Result<()> {
        if definition.name.trim().is_empty() {
            return Err(anyhow!("subagent definition name is required"));
        }
        self.definitions.insert(definition.name.clone(), definition);
        Ok(())
    }

    pub fn definitions(&self) -> impl Iterator<Item = &SubagentDefinition> {
        self.definitions.values()
    }

    pub fn runs(&self) -> impl Iterator<Item = &SubagentRun> {
        self.runs.values()
    }

    pub fn get_run(&self, id: &str) -> Option<&SubagentRun> {
        self.runs.get(id)
    }

    pub fn spawn(&mut self, request: SubagentSpawnRequest) -> Result<SubagentSpawnResult> {
        if self
            .runs
            .values()
            .filter(|run| run.status == SubagentStatus::Running)
            .count()
            >= self.config.max_threads
        {
            return Ok(SubagentSpawnResult {
                run_id: String::new(),
                success: false,
                error: Some("maximum concurrent subagents reached".to_string()),
            });
        }

        if request.depth > self.config.max_depth {
            return Ok(SubagentSpawnResult {
                run_id: String::new(),
                success: false,
                error: Some("maximum subagent nesting depth reached".to_string()),
            });
        }

        let run_id = format!("subagent-{}", self.next_id);
        self.next_id += 1;

        let run = SubagentRun {
            id: run_id.clone(),
            name: request.name,
            task: request.task,
            parent_id: request.parent_id,
            depth: request.depth,
            status: SubagentStatus::Running,
            started_at: Utc::now(),
            completed_at: None,
            output: None,
            error: None,
        };
        self.runs.insert(run_id.clone(), run);

        Ok(SubagentSpawnResult {
            run_id,
            success: true,
            error: None,
        })
    }

    pub fn complete(&mut self, id: &str, output: impl Into<String>) -> Result<()> {
        let run = self
            .runs
            .get_mut(id)
            .ok_or_else(|| anyhow!("unknown subagent run '{}'", id))?;
        run.status = SubagentStatus::Completed;
        run.completed_at = Some(Utc::now());
        run.output = Some(output.into());
        Ok(())
    }

    pub fn fail(&mut self, id: &str, error: impl Into<String>) -> Result<()> {
        let run = self
            .runs
            .get_mut(id)
            .ok_or_else(|| anyhow!("unknown subagent run '{}'", id))?;
        run.status = SubagentStatus::Failed;
        run.completed_at = Some(Utc::now());
        run.error = Some(error.into());
        Ok(())
    }
}

impl Default for SubagentManager {
    fn default() -> Self {
        Self::new(SubagentConfig {
            max_threads: 6,
            max_depth: 1,
            job_max_runtime_seconds: 300,
        })
    }
}
