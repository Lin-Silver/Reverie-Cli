use super::{Result, Tui};
use serde_json::json;

impl Tui {
    pub(super) async fn skills_command(&mut self, args: &[String]) -> Result<()> {
        let operation = args.first().map(String::as_str).unwrap_or("list");
        let direct_pin = !matches!(
            operation,
            "list"
                | "refresh"
                | "pin"
                | "use"
                | "unpin"
                | "remove"
                | "clear"
                | "search"
                | "inspect"
                | "resource"
                | "help"
        );
        let operation = match operation {
            "use" => "pin",
            "remove" => "unpin",
            _ if direct_pin => "pin",
            other => other,
        };
        let data = match operation {
            "list" | "refresh" => {
                let action = if operation == "refresh" {
                    "refreshSkills"
                } else {
                    "listSkills"
                };
                let response = self
                    .request(action, json!({"sessionId":self.session}))
                    .await?;
                let state = &response["skills"];
                let mut lines = vec![format!(
                    "Skills: {} · invalid {} · shadowed {} · pins {}/{}",
                    state["count"],
                    state["invalid_count"],
                    state["shadowed_count"],
                    state["pinned"]["names"].as_array().map_or(0, Vec::len),
                    state["pinned"]["max"]
                )];
                for record in state["records"].as_array().into_iter().flatten() {
                    lines.push(format!(
                        "{}{}{} · {}\n  {}",
                        record["name"].as_str().unwrap_or_default(),
                        if record["pinned"] == true {
                            " [pinned]"
                        } else {
                            ""
                        },
                        if record["shadowed"] == true {
                            " [shadowed]"
                        } else {
                            ""
                        },
                        record["scope"].as_str().unwrap_or_default(),
                        record["summary"].as_str().unwrap_or_default()
                    ));
                }
                for issue in state["errors"].as_array().into_iter().flatten() {
                    lines.push(format!(
                        "Invalid {}: {}",
                        issue["path"].as_str().unwrap_or_default(),
                        issue["message"].as_str().unwrap_or_default()
                    ));
                }
                for name in state["pinned"]["unresolved"]
                    .as_array()
                    .into_iter()
                    .flatten()
                {
                    lines.push(format!(
                        "Unavailable pinned skill: {}",
                        name.as_str().unwrap_or_default()
                    ));
                }
                self.screen.print(&lines.join("\n"))?;
                return Ok(());
            }
            "pin" | "unpin" | "clear" => {
                let name = args
                    .iter()
                    .skip(if direct_pin { 0 } else { 1 })
                    .cloned()
                    .collect::<Vec<_>>()
                    .join(" ");
                if operation != "clear" && name.is_empty() {
                    return Err("Supply a skill name.".into());
                }
                let action = match operation {
                    "pin" => "pinSkill",
                    "unpin" => "unpinSkill",
                    _ => "clearPinnedSkills",
                };
                let result = self
                    .request(action, json!({"sessionId":self.session,"skill":name}))
                    .await?;
                self.screen.print(&format!(
                    "Skill {}: {}",
                    result["status"].as_str().unwrap_or_default(),
                    result["name"].as_str().unwrap_or_default()
                ))?;
                self.refresh().await?;
                return Ok(());
            }
            "search" => {
                let query = args.iter().skip(1).cloned().collect::<Vec<_>>().join(" ");
                if query.is_empty() {
                    return Err("Use /skills search <keywords>.".into());
                }
                json!({"operation":"search","query":query,"force_refresh":true})
            }
            "inspect" | "resource" => {
                let name = args.get(1).ok_or("Supply a skill name.")?;
                let resource = operation == "resource";
                let offset = args
                    .get(if resource { 3 } else { 2 })
                    .map(|text| text.parse::<usize>())
                    .transpose()?;
                let mut request = json!({"operation":if resource {"read_resource"}else{"inspect"},"skill_name":name,"body_offset":offset,"force_refresh":true});
                if resource {
                    request["resource_path"] =
                        json!(args.get(2).ok_or("Supply a skill-relative text path.")?);
                }
                request
            }
            "help" => {
                self.screen.print("/skills list · refresh · search <keywords>\n/skills inspect <name> [body-offset]\n/skills resource <name> <relative-path> [body-offset]\n/skills pin <name> · unpin <name> · clear\nPins belong to the current conversation. Read every chunk before using a skill.")?;
                return Ok(());
            }
            _ => return Err("Unknown skills command. Use /skills help.".into()),
        };
        let mut data = data;
        data["sessionId"] = json!(self.session);
        let response = self.request("lookupSkill", data).await?;
        let result = &response["data"];
        if let Some(body) = result["body"].as_str() {
            let visible = body
                .chars()
                .map(|ch| {
                    if ch.is_control() && !matches!(ch, '\n' | '\r' | '\t') {
                        ch.escape_default().to_string()
                    } else {
                        ch.to_string()
                    }
                })
                .collect::<String>();
            self.screen.print(&visible)?;
            if result["complete"] == false {
                self.screen.print(&format!(
                    "More text remains. Continue with body-offset {}.",
                    result["next_body_offset"]
                ))?;
            }
        } else {
            self.screen.print(&serde_json::to_string_pretty(result)?)?;
        }
        Ok(())
    }
}
