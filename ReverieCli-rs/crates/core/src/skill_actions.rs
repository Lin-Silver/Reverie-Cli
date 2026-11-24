use crate::{
    Kernel, Result, config, models,
    skills::{MAX_PINNED, SkillCatalog, normalize},
};
use reverie_protocol::{SkillLookupRequest, SkillsState};
use serde_json::{Map, Value, json};
use std::{fs, path::Path, sync::Arc};

impl Kernel {
    pub(crate) fn skill_catalog_at(
        &mut self,
        root: &Path,
        mode: &str,
        refresh: bool,
    ) -> Result<Arc<SkillCatalog>> {
        let key = (root.to_owned(), mode.to_owned());
        if refresh || !self.skill_catalogs.contains_key(&key) {
            let catalog = Arc::new(SkillCatalog::discover(root, &self.app_root, mode)?);
            self.skill_catalogs.insert(key.clone(), catalog);
        }
        Ok(self.skill_catalogs[&key].clone())
    }
    pub(crate) fn pinned_skills(&mut self, session: Option<&str>) -> Result<Vec<String>> {
        let value = if let Some(id) = session {
            let page = self.session_store()?.page(id, None, 1)?;
            page.metadata
                .get("pinned_skills")
                .cloned()
                .or_else(|| {
                    page.metadata
                        .get("runtime_config")
                        .and_then(|snapshot| snapshot.get("pinned_skills"))
                        .cloned()
                })
                .unwrap_or_else(|| json!([]))
        } else {
            match fs::read(self.project_data_dir.join("desktop/draft-skills.json")) {
                Ok(bytes) => serde_json::from_slice(&bytes)?,
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => json!([]),
                Err(error) => return Err(error.into()),
            }
        };
        let array = value
            .as_array()
            .ok_or("Saved skill pins must be an array.")?;
        let mut pins = Vec::new();
        for value in array.iter().take(MAX_PINNED) {
            let name = value
                .as_str()
                .ok_or("Saved skill pin must be a string.")?
                .trim();
            if !normalize(name).is_empty()
                && !pins
                    .iter()
                    .any(|existing: &String| normalize(existing) == normalize(name))
            {
                pins.push(name.to_owned());
            }
        }
        Ok(pins)
    }
    fn write_skill_pins(
        &mut self,
        session: Option<&str>,
        pins: &[String],
        expected: Option<i64>,
    ) -> Result<()> {
        if let Some(id) = session {
            let page = self.session_store()?.page(id, None, 1)?;
            let defaults = self.config.effective()?;
            let mut snapshot = page
                .metadata
                .get("runtime_config")
                .cloned()
                .unwrap_or_else(|| models::capture(&defaults));
            if !snapshot.is_object() {
                return Err("Saved conversation configuration is invalid.".into());
            }
            snapshot["pinned_skills"] = json!(pins);
            self.session_store()?.update_metadata(
                id,
                Map::from_iter([
                    ("pinned_skills".into(), json!(pins)),
                    ("runtime_config".into(), snapshot),
                ]),
                expected.unwrap_or(page.revision),
            )?;
        } else {
            config::atomic_json(
                &self.project_data_dir.join("desktop/draft-skills.json"),
                &json!(pins),
            )?;
        }
        Ok(())
    }
    pub(crate) fn skills_state(
        &mut self,
        session: Option<&str>,
        refresh: bool,
    ) -> Result<SkillsState> {
        let pins = self.pinned_skills(session)?;
        let root = self.project_root.clone();
        let configuration = self.effective_config(session)?;
        let mode = configuration["mode"].as_str().unwrap_or("reverie");
        let catalog = self.skill_catalog_at(&root, mode, refresh)?;
        Ok(catalog.state(mode, &pins))
    }
    pub(crate) fn handle_skills(
        &mut self,
        action: &str,
        payload: &Value,
    ) -> Result<(&'static str, Value)> {
        let session = if payload["draft"] == true {
            None
        } else {
            payload["sessionId"]
                .as_str()
                .map(str::to_owned)
                .or_else(|| self.view_session.clone())
        };
        if action == "listSkills" || action == "refreshSkills" {
            return Ok((
                "skills",
                json!({"skills":self.skills_state(session.as_deref(), action=="refreshSkills")?}),
            ));
        }
        let pins = self.pinned_skills(session.as_deref())?;
        let root = self.project_root.clone();
        let configuration = self.effective_config(session.as_deref())?;
        let mode = configuration["mode"].as_str().unwrap_or("reverie");
        let catalog = self.skill_catalog_at(&root, mode, action == "pinSkill")?;
        if action == "lookupSkill" {
            let request: SkillLookupRequest = serde_json::from_value(payload.clone())?;
            let catalog = if request.force_refresh == Some(true) {
                self.skill_catalog_at(&root, mode, true)?
            } else {
                catalog
            };
            return Ok((
                "skill.lookup",
                json!({"data":catalog.lookup(&request, &pins)?}),
            ));
        }
        let identifier = payload["skill"]
            .as_str()
            .or_else(|| payload["name"].as_str())
            .or_else(|| payload["key"].as_str())
            .unwrap_or("")
            .trim();
        if action == "inspectSkill" {
            let record = if catalog.name(identifier).is_some() {
                catalog.inspect(identifier, &pins)?
            } else {
                Value::Null
            };
            return Ok(("skill.inspect", json!({"record":record})));
        }
        if identifier.is_empty() && action != "clearPinnedSkills" {
            return Err("Skill name is required.".into());
        }
        let expected = payload
            .get("expectedRevision")
            .map(|value| {
                value
                    .as_i64()
                    .ok_or("Skill pin revision must be an integer.")
            })
            .transpose()?;
        let mut next = pins.clone();
        let mut released = Vec::new();
        let name = catalog
            .name(identifier)
            .unwrap_or(identifier.trim_start_matches('$'))
            .to_owned();
        let key = normalize(&name);
        let status = match action {
            "clearPinnedSkills" => {
                released = std::mem::take(&mut next);
                "cleared"
            }
            "pinSkill" if catalog.name(identifier).is_none() => "missing",
            "pinSkill" if next.iter().any(|name| normalize(name) == key) => "already",
            "pinSkill" if next.len() >= MAX_PINNED => "full",
            "pinSkill" => {
                next.push(name.clone());
                "pinned"
            }
            "unpinSkill" => {
                let previous = next.len();
                next.retain(|name| normalize(name) != key);
                if next.len() == previous {
                    "missing"
                } else {
                    "unpinned"
                }
            }
            _ => return Err("Unknown skill action.".into()),
        };
        if next != pins {
            self.write_skill_pins(session.as_deref(), &next, expected)?;
        }
        Ok((
            "skill.pinned",
            json!({"status":status,"name":name,"released":released,"skills":self.skills_state(session.as_deref(), false)?}),
        ))
    }
}
