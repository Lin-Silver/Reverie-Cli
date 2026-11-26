use super::*;
use uuid::Uuid;

const STATE: &str = "artifacts/atlas/atlas_state.json";

fn defaults() -> Value {
    json!({"objective":"","delivery_mode":"full_delivery","complexity_tier":"tier3","contract_summary":"","user_requested_implementation":true,"contract_confirmed":false,"confirmation_notes":"","master_document_path":"artifacts/Master Document.md","appendix_paths":[],"success_criteria":[],"constraints":[],"document_manifest":[],"slices":[],"verifications":[],"blockers":[],"checkpoints":[],"created_at":crate::session::now(),"updated_at":crate::session::now(),"last_action":"","final_report_path":"artifacts/atlas/final_delivery_report.md","native_revision":0})
}

fn load(root: &Path) -> Result<Value> {
    let path = safe_path(root, STATE)?;
    let state = if path.is_file() {
        read_json(&path)?
    } else {
        defaults()
    };
    for key in [
        "slices",
        "verifications",
        "blockers",
        "checkpoints",
        "appendix_paths",
        "success_criteria",
        "constraints",
    ] {
        if state.get(key).is_some_and(|field| !field.is_array()) {
            return Err(format!("Invalid Atlas {key}; original state was preserved.").into());
        }
    }
    let mut merged = defaults();
    merged
        .as_object_mut()
        .unwrap()
        .extend(state.as_object().unwrap().clone());
    Ok(merged)
}

pub(super) fn guidance(root: &Path, configuration: &Value) -> Result<String> {
    let state = load(root)?;
    Ok(format!(
        "## Reverie-Atlas document-driven execution\nResearch before broad implementation. Inspect artifacts/atlas/resume_index.md and the persisted Atlas state when resuming. Maintain a master document, requirements/design/tasks and subsystem appendices with evidence, interfaces, dependencies, constraints, failures and verification. Record the user's actual confirmation using userInput; a model assertion is not authorization. Implement the next documented slice completely after scope is confirmed, update the ledger and documents after actual tests, and persist until the user's requested delivery is complete. Use atlas_delivery_orchestrator for contract, slices, verification, blockers, checkpoints and closure. Verification entries describe reported results; never fabricate their commands or evidence. Current Atlas configuration: {}\nCurrent persisted delivery state: {}",
        serde_json::to_string(&configuration["atlas_mode"])?,
        serde_json::to_string(&state)?
    ))
}

pub(super) fn definition() -> Value {
    let mut properties = serde_json::Map::from_iter([(
        "action".into(),
        json!({"type":"string","enum":["bootstrap_delivery","register_contract","plan_slices","record_slice","record_verification","record_blocker","resolve_blocker","sync_documents","checkpoint_delivery","assess_completion","prepare_final_report"]}),
    )]);
    for key in [
        "objective",
        "contract_summary",
        "delivery_mode",
        "complexity_tier",
        "master_document_path",
        "confirmation_notes",
        "slice_id",
        "title",
        "status",
        "document_anchor",
        "notes",
        "kind",
        "summary",
        "command",
        "blocker_id",
        "detail",
        "severity",
        "focus",
        "next_action",
        "report_path",
    ] {
        properties.insert(key.into(), json!({"type":"string"}));
    }
    for key in [
        "appendix_paths",
        "appendix_titles",
        "success_criteria",
        "constraints",
        "slice_titles",
        "document_paths",
        "implementation_targets",
        "verification_plan",
        "verification_results",
        "delivered_changes",
        "open_questions",
        "dependencies",
        "evidence_paths",
        "impacted_slices",
        "unblockers",
        "open_risks",
        "updated_docs",
    ] {
        properties.insert(
            key.into(),
            json!({"type":"array","items":{"type":"string"}}),
        );
    }
    for key in [
        "contract_confirmed",
        "user_requested_implementation",
        "create_placeholders",
        "replace_existing_slices",
        "passed",
        "strict",
    ] {
        properties.insert(key.into(), json!({"type":"boolean"}));
    }
    json!({"type":"function","function":{"name":"atlas_delivery_orchestrator","description":"Persist the Atlas contract, document baseline, implementation slices, reported verification, blockers and handoff. Assess actual document identity before closure; incomplete work cannot be silently marked complete.","parameters":{"type":"object","properties":properties,"required":["action"]}}})
}

fn slice_id(state: &Value, args: &Value) -> Result<String> {
    let id = text(args, "slice_id");
    state["slices"]
        .as_array()
        .unwrap()
        .iter()
        .find(|item| {
            if id.is_empty() {
                item["title"] == text(args, "title")
            } else {
                item["slice_id"] == id
            }
        })
        .and_then(|item| item["slice_id"].as_str())
        .map(str::to_owned)
        .ok_or_else(|| "Atlas slice was not found; plan it first.".into())
}

fn snapshots(root: &Path, state: &Value) -> Result<Vec<Value>> {
    let mut paths = vec![text(state, "master_document_path").to_owned()];
    paths.extend(strings(state, "appendix_paths")?);
    paths.into_iter().map(|relative| {
        let path = safe_path(root, &relative)?;
        if !path.is_file() { return Ok(json!({"path":relative,"exists":false,"nonempty":false})); }
        let bytes = read_bytes(&path, 16*1024*1024)?;
        let body = std::str::from_utf8(&bytes)?.trim_start_matches('\u{feff}');
        let nonempty = body.lines().any(|line| !line.trim().is_empty() && !line.trim().starts_with('#'));
        Ok(json!({"path":relative,"exists":true,"nonempty":nonempty,"sha256":digest(&bytes),"bytes":bytes.len(),"headings":body.lines().filter(|line|line.starts_with('#')).collect::<Vec<_>>()}))
    }).collect()
}

fn criteria_coverage(state: &Value) -> Result<Vec<Value>> {
    let mut evidence = vec![
        text(state, "objective").to_owned(),
        text(state, "contract_summary").to_owned(),
    ];
    for slice in state["slices"].as_array().unwrap() {
        if slice["status"] == "completed" {
            evidence.push(text(slice, "title").to_owned());
        }
        evidence.extend(strings(slice, "delivered_changes")?);
    }
    evidence.extend(
        state["verifications"]
            .as_array()
            .unwrap()
            .iter()
            .map(|item| text(item, "summary").to_owned()),
    );
    let completed = caseless::default_case_fold_str(&evidence.join(" "));
    Ok(strings(state, "success_criteria")?.into_iter().map(|criterion| {
        let folded = caseless::default_case_fold_str(&criterion);
        let matched = folded.split(|ch: char| !ch.is_alphanumeric() && ch != '_')
            .filter(|word| word.chars().count() > 3 && completed.contains(word)).collect::<Vec<_>>();
        json!({"criterion":criterion,"covered":!matched.is_empty() || completed.contains(&folded),"matched_words":matched})
    }).collect())
}

fn assess(root: &Path, state: &Value) -> Result<Value> {
    let documents = snapshots(root, state)?;
    let mut missing = Vec::new();
    if text(state, "objective").is_empty() {
        missing.push("Atlas objective is missing.".to_owned());
    }
    if state["user_requested_implementation"] == true
        && state["delivery_mode"] == "full_delivery"
        && state["contract_confirmed"] != true
    {
        missing.push("The user has not confirmed the document baseline.".into());
    }
    if documents.iter().any(|item| item["nonempty"] != true) {
        missing.push("Required documents are missing or contain only headings.".into());
    }
    let open = state["slices"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|item| !["completed", "cancelled"].contains(&text(item, "status")))
        .cloned()
        .collect::<Vec<_>>();
    if state["user_requested_implementation"] == true {
        if !open.is_empty() {
            missing.push("Implementation slices remain unfinished.".into());
        }
        if !state["slices"]
            .as_array()
            .unwrap()
            .iter()
            .any(|item| item["status"] == "completed")
        {
            missing.push("No implementation slice was completed.".into());
        }
        if state["verifications"].as_array().unwrap().is_empty() {
            missing.push("No reported verification was recorded.".into());
        }
    }
    if state["blockers"]
        .as_array()
        .unwrap()
        .iter()
        .any(|item| item["status"] == "open")
    {
        missing.push("Open blockers remain.".into());
    }
    if state["verifications"]
        .as_array()
        .unwrap()
        .iter()
        .any(|item| item["passed"] != true)
    {
        missing.push("Failed verification records remain.".into());
    }
    if state["success_criteria"].as_array().unwrap().is_empty() {
        missing.push("Success criteria are missing.".into());
    }
    let coverage = criteria_coverage(state)?;
    for criterion in coverage.iter().filter(|item| item["covered"] != true) {
        missing.push(format!(
            "Success criterion not covered: {}",
            text(criterion, "criterion")
        ));
    }
    for verification in state["verifications"].as_array().unwrap() {
        if let Some(evidence) = verification["evidence_hashes"].as_object() {
            for (relative, identity) in evidence {
                let path = safe_path(root, relative)?;
                if !path.is_file()
                    || digest(&read_bytes(&path, 16 * 1024 * 1024)?)
                        != identity.as_str().unwrap_or("")
                {
                    missing.push(format!(
                        "Verification evidence changed or disappeared: {relative}"
                    ));
                }
            }
        }
    }
    Ok(
        json!({"ready":missing.is_empty(),"objective":state["objective"],"delivery_mode":state["delivery_mode"],"open_slices":open,"missing_conditions":missing,"document_manifest":documents,"criteria_coverage":coverage,"coverage_provenance":"text coverage heuristic over recorded contract and delivery content","verification_provenance":"reported workflow results, not independently rerun by this assessment"}),
    )
}

fn render(root: &Path, state: &Value) -> Result<()> {
    let mut tracker = format!(
        "# Atlas Delivery Tracker\n\n{}\n\n",
        text(state, "objective")
    );
    for slice in state["slices"].as_array().unwrap() {
        tracker.push_str(&format!(
            "- [{}] {} — {} ({})\n",
            if slice["status"] == "completed" {
                "x"
            } else {
                " "
            },
            text(slice, "slice_id"),
            text(slice, "title"),
            text(slice, "status")
        ));
    }
    write_bytes(
        &safe_path(root, "artifacts/atlas/delivery_tracker.md")?,
        tracker.as_bytes(),
    )?;
    write_bytes(&safe_path(root, "artifacts/task.md")?, tracker.as_bytes())?;
    let resume = format!(
        "# Atlas Resume Index\n\nStart with [persisted delivery state](atlas_state.json), [tracker](delivery_tracker.md), [document manifest](document_manifest.json), and [handoff](handoff_summary.md).\n\nObjective: {}\nLast action: {}\n",
        text(state, "objective"),
        text(state, "last_action")
    );
    write_bytes(
        &safe_path(root, "artifacts/atlas/resume_index.md")?,
        resume.as_bytes(),
    )?;
    write_bytes(
        &safe_path(root, "artifacts/atlas/delivery_charter.md")?,
        format!(
            "# Atlas Delivery Charter\n\n{}\n\n{}\n\n## Success criteria\n{}\n",
            text(state, "objective"),
            text(state, "contract_summary"),
            strings(state, "success_criteria")?
                .iter()
                .map(|criterion| format!("- {criterion}"))
                .collect::<Vec<_>>()
                .join("\n")
        )
        .as_bytes(),
    )?;
    Ok(())
}

pub(super) fn execute(args: &Value, root: &Path) -> Result<Value> {
    let action = text(args, "action");
    if action == "assess_completion" {
        return object_result(assess(root, &load(root)?)?);
    }
    let _lock = lock(&safe_path(root, "artifacts/atlas/native.lock")?)?;
    let mut state = load(root)?;
    match action {
        "bootstrap_delivery" | "register_contract" => {
            for key in [
                "objective",
                "contract_summary",
                "delivery_mode",
                "complexity_tier",
                "master_document_path",
                "confirmation_notes",
            ] {
                if args.get(key).is_some() {
                    state[key] = json!(text(args, key));
                }
            }
            if text(&state, "objective").is_empty() {
                return Err("Atlas objective is required.".into());
            }
            if ![
                "research_only",
                "documentation_only",
                "full_delivery",
                "session_continuation",
            ]
            .contains(&text(&state, "delivery_mode"))
                || !["tier1", "tier2", "tier3", "tier4"].contains(&text(&state, "complexity_tier"))
            {
                return Err("Invalid Atlas delivery mode or complexity tier.".into());
            }
            for key in ["user_requested_implementation", "contract_confirmed"] {
                if let Some(value) = args.get(key) {
                    if !value.is_boolean() {
                        return Err("Atlas confirmation fields require explicit booleans.".into());
                    }
                    state[key] = value.clone();
                }
            }
            for key in ["appendix_paths", "success_criteria", "constraints"] {
                if args.get(key).is_some() {
                    state[key] = json!(strings(args, key)?);
                }
            }
            if args.get("appendix_titles").is_some() && args.get("appendix_paths").is_none() {
                state["appendix_paths"] = json!(
                    strings(args, "appendix_titles")?
                        .iter()
                        .enumerate()
                        .map(|(i, title)| format!(
                            "artifacts/Appendix {} - {}.md",
                            i + 1,
                            title.replace(['/', '\\', ':'], "_")
                        ))
                        .collect::<Vec<_>>()
                );
            }
            safe_path(root, text(&state, "master_document_path"))?;
            for path in strings(&state, "appendix_paths")? {
                safe_path(root, &path)?;
            }
            if args["create_placeholders"] == true {
                for document in snapshots(root, &state)? {
                    if document["exists"] != true {
                        write_bytes(
                            &safe_path(root, text(&document, "path"))?,
                            b"# Document\n\n",
                        )?;
                    }
                }
            }
        }
        "plan_slices" => {
            let titles = strings(args, "slice_titles")?;
            if titles.is_empty() {
                return Err("Atlas slice_titles are required.".into());
            }
            if args["replace_existing_slices"] == true
                && state["slices"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .any(|item| item["status"] != "planned")
            {
                return Err(
                    "Cannot replace an Atlas plan that already contains execution state.".into(),
                );
            }
            if args["replace_existing_slices"] == true {
                state["slices"] = json!([]);
            }
            for title in titles {
                if state["slices"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .any(|item| item["title"] == title)
                {
                    continue;
                }
                let number = state["slices"].as_array().unwrap().len() + 1;
                state["slices"].as_array_mut().unwrap().push(json!({"slice_id":format!("slice-{number:03}"),"title":title,"status":"planned","document_paths":[],"implementation_targets":[],"verification_plan":[],"verification_results":[],"delivered_changes":[],"open_questions":[],"dependencies":[],"created_at":crate::session::now(),"updated_at":crate::session::now()}));
            }
        }
        "record_slice" => {
            let id = slice_id(&state, args)?;
            let slice = state["slices"]
                .as_array_mut()
                .unwrap()
                .iter_mut()
                .find(|item| item["slice_id"] == id)
                .unwrap();
            if args.get("status").is_some() {
                let status = text(args, "status");
                if ![
                    "planned",
                    "in_progress",
                    "completed",
                    "blocked",
                    "cancelled",
                ]
                .contains(&status)
                {
                    return Err("Invalid Atlas slice status.".into());
                }
                slice["status"] = json!(status);
            }
            for key in ["document_anchor", "notes"] {
                if args.get(key).is_some() {
                    slice[key] = json!(text(args, key));
                }
            }
            for key in [
                "document_paths",
                "implementation_targets",
                "verification_plan",
                "verification_results",
                "delivered_changes",
                "open_questions",
                "dependencies",
            ] {
                if args.get(key).is_some() {
                    slice[key] = json!(strings(args, key)?);
                }
            }
            slice["updated_at"] = json!(crate::session::now());
        }
        "record_verification" => {
            let id = slice_id(&state, args)?;
            if text(args, "summary").is_empty() || !args["passed"].is_boolean() {
                return Err("Verification requires summary and an explicit passed boolean.".into());
            }
            let mut evidence = serde_json::Map::new();
            for relative in strings(args, "evidence_paths")? {
                let bytes = read_bytes(&safe_path(root, &relative)?, 16 * 1024 * 1024)?;
                evidence.insert(relative, json!(digest(&bytes)));
            }
            state["verifications"].as_array_mut().unwrap().push(json!({"verification_id":Uuid::new_v4().simple().to_string(),"slice_id":id,"kind":text(args,"kind"),"summary":text(args,"summary"),"command":text(args,"command"),"passed":args["passed"],"evidence_paths":strings(args,"evidence_paths")?,"evidence_hashes":evidence,"recorded_at":crate::session::now()}));
        }
        "record_blocker" => {
            if text(args, "title").is_empty() {
                return Err("Atlas blocker title is required.".into());
            }
            state["blockers"].as_array_mut().unwrap().push(json!({"blocker_id":format!("blocker-{}",Uuid::new_v4().simple()),"title":text(args,"title"),"detail":text(args,"detail"),"severity":text(args,"severity"),"status":"open","impacted_slices":strings(args,"impacted_slices")?,"unblockers":strings(args,"unblockers")?,"created_at":crate::session::now()}));
        }
        "resolve_blocker" => {
            let blocker = state["blockers"]
                .as_array_mut()
                .unwrap()
                .iter_mut()
                .find(|item| item["blocker_id"] == text(args, "blocker_id"))
                .ok_or("Atlas blocker was not found.")?;
            blocker["status"] = json!("resolved");
            blocker["notes"] = json!(text(args, "notes"));
            blocker["resolved_at"] = json!(crate::session::now());
        }
        "sync_documents" => {
            state["document_manifest"] = json!(snapshots(root, &state)?);
            write_json(
                &safe_path(root, "artifacts/atlas/document_manifest.json")?,
                &state["document_manifest"],
            )?;
            write_bytes(
                &safe_path(root, "artifacts/atlas/document_manifest.md")?,
                format!(
                    "# Atlas Document Manifest\n\n{}\n",
                    serde_json::to_string_pretty(&state["document_manifest"])?
                )
                .as_bytes(),
            )?;
        }
        "checkpoint_delivery" => {
            let packet = json!({"focus":text(args,"focus"),"summary":text(args,"summary"),"next_action":text(args,"next_action"),"open_risks":strings(args,"open_risks")?,"updated_docs":strings(args,"updated_docs")?,"recorded_at":crate::session::now()});
            state["checkpoints"]
                .as_array_mut()
                .unwrap()
                .push(packet.clone());
            write_bytes(
                &safe_path(root, "artifacts/atlas/handoff_summary.md")?,
                format!(
                    "# Atlas Handoff\n\n{}\n",
                    serde_json::to_string_pretty(&packet)?
                )
                .as_bytes(),
            )?;
        }
        "prepare_final_report" => {
            let assessment = assess(root, &state)?;
            if args["strict"] != false && assessment["ready"] != true {
                return Err(format!(
                    "Atlas completion gates remain: {}",
                    assessment["missing_conditions"]
                )
                .into());
            }
            let report = if text(args, "report_path").is_empty() {
                text(&state, "final_report_path")
            } else {
                text(args, "report_path")
            };
            write_bytes(
                &safe_path(root, report)?,
                format!(
                    "# Atlas Delivery Report\n\n{}\n\n{}\n",
                    text(&state, "objective"),
                    serde_json::to_string_pretty(&assessment)?
                )
                .as_bytes(),
            )?;
            state["final_report_path"] = json!(report);
            state["last_assessment"] = assessment;
        }
        _ => return Err("Unknown Atlas action.".into()),
    }
    state["updated_at"] = json!(crate::session::now());
    state["last_action"] = json!(action);
    state["native_revision"] = json!(
        state["native_revision"]
            .as_u64()
            .unwrap_or(0)
            .checked_add(1)
            .ok_or("Atlas revision overflow.")?
    );
    render(root, &state)?;
    write_json(&safe_path(root, STATE)?, &state)?;
    object_result(json!({"state":state,"state_path":STATE}))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn completion_checks_criterion_coverage_and_explicit_implementation_intent() {
        let root = tempfile::tempdir().unwrap();
        let p = root.path();
        fs::create_dir(p.join("artifacts")).unwrap();
        fs::write(
            p.join("artifacts/Master Document.md"),
            "# Contract\n\nInspect exact original documents.\n",
        )
        .unwrap();
        execute(&json!({"action":"bootstrap_delivery","objective":"Audit original documents","delivery_mode":"documentation_only","user_requested_implementation":false,"success_criteria":["Independent unrelated capability", "Straße"]}), p).unwrap();
        let incomplete = assess(p, &load(p).unwrap()).unwrap();
        assert_eq!(incomplete["ready"], false);
        assert!(
            incomplete["criteria_coverage"]
                .as_array()
                .unwrap()
                .iter()
                .all(|item| item["covered"] == false)
        );
        execute(&json!({"action":"register_contract","contract_summary":"Independent unrelated capability recorded with STRASSE"}), p).unwrap();
        let complete = assess(p, &load(p).unwrap()).unwrap();
        assert_eq!(complete["ready"], true);
        assert_eq!(
            complete["criteria_coverage"][1]["matched_words"],
            json!(["strasse"])
        );
        execute(
            &json!({"action":"register_contract","user_requested_implementation":true}),
            p,
        )
        .unwrap();
        let incomplete = assess(p, &load(p).unwrap()).unwrap();
        assert_eq!(incomplete["ready"], false);
        assert!(
            incomplete["missing_conditions"]
                .as_array()
                .unwrap()
                .iter()
                .any(|item| item.as_str().unwrap().contains("No implementation slice"))
        );
    }

    #[test]
    fn atlas_resumes_and_rejects_missing_or_changed_evidence() {
        let root = tempfile::tempdir().unwrap();
        let p = root.path();
        execute(&json!({"action":"bootstrap_delivery","objective":"Implement a bounded feature","success_criteria":["Real verification"],"contract_confirmed":true,"create_placeholders":true}),p).unwrap();
        execute(
            &json!({"action":"plan_slices","slice_titles":["Implementation"]}),
            p,
        )
        .unwrap();
        assert!(
            !assess(p, &load(p).unwrap()).unwrap()["ready"]
                .as_bool()
                .unwrap()
        );
        write_bytes(
            &safe_path(p, "artifacts/Master Document.md").unwrap(),
            b"# Design\n\nActual document body\n",
        )
        .unwrap();
        write_bytes(
            &safe_path(p, "artifacts/proof.json").unwrap(),
            b"{\"passed\":true}\n",
        )
        .unwrap();
        execute(&json!({"action":"record_slice","slice_id":"slice-001","status":"completed","delivered_changes":["Implemented feature"]}),p).unwrap();
        execute(&json!({"action":"record_verification","slice_id":"slice-001","summary":"Checked real behavior","passed":true,"evidence_paths":["artifacts/proof.json"]}),p).unwrap();
        assert_eq!(assess(p, &load(p).unwrap()).unwrap()["ready"], true);
        write_bytes(&safe_path(p, "artifacts/proof.json").unwrap(), b"changed").unwrap();
        assert_eq!(assess(p, &load(p).unwrap()).unwrap()["ready"], false);
        assert!(execute(&json!({"action":"prepare_final_report"}), p).is_err());
        let state_path = safe_path(p, STATE).unwrap();
        fs::write(&state_path, b"invalid").unwrap();
        assert!(load(p).is_err());
        assert_eq!(fs::read(state_path).unwrap(), b"invalid");
    }
}
