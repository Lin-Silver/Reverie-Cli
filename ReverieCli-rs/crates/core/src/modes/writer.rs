use super::*;
use regex::Regex;
use std::collections::HashSet;

mod quality;

const SCHEMA: &str = "reverie.writer.project.v1";
const DOCUMENTS: &[(&str, &str, &str)] = &[
    ("world_bible", "01-world-bible.md", "World Bible"),
    ("cast_bible", "02-cast-bible.md", "Cast Bible"),
    (
        "story_architecture",
        "03-story-architecture.md",
        "Story Architecture",
    ),
    ("style_guide", "04-style-guide.md", "Style Guide"),
    ("roadmap", "05-roadmap.md", "Chapter Roadmap"),
];

fn number(value: &Value, key: &str, default: u64) -> Result<u64> {
    match value.get(key) {
        None | Some(Value::Null) => Ok(default),
        Some(value) => value
            .as_u64()
            .ok_or_else(|| format!("Writer {key} must be a nonnegative integer.").into()),
    }
}

fn scaled_chars(value: u64, percent: u64) -> Result<u64> {
    u64::try_from(u128::from(value) * u128::from(percent) / 100)
        .map_err(|_| "Writer length recommendation exceeds the supported integer range.".into())
}

fn next_chapter(chapter: u64) -> Result<u64> {
    chapter
        .checked_add(1)
        .ok_or_else(|| "Writer chapter exceeds the supported integer range.".into())
}

fn novel_id(raw: &str) -> Result<String> {
    let mut result = String::new();
    let mut separator = false;
    for ch in raw.trim().chars() {
        if ch.is_alphanumeric() || matches!(ch, '-' | '_' | '.') {
            result.push(ch);
            separator = false;
        } else if !separator {
            result.push('-');
            separator = true;
        }
    }
    let result = result
        .trim_matches(['-', '_', '.'])
        .chars()
        .take(80)
        .collect::<String>();
    if result.is_empty() {
        return Err("novel_id must contain at least one letter or number.".into());
    }
    Ok(result)
}

fn output(root: &Path, args: &Value) -> Result<PathBuf> {
    safe_path(
        root,
        if text(args, "output_dir").is_empty() {
            "novels"
        } else {
            text(args, "output_dir")
        },
    )
}

fn state_path(project: &Path) -> Result<PathBuf> {
    safe_path(project, "tracking/state.json")
}
fn artifact(project: &Path, folder: &str, chapter: u64, extension: &str) -> Result<PathBuf> {
    safe_path(
        project,
        &format!(
            "{}chapter-{chapter:04}.{extension}",
            if folder.is_empty() {
                String::new()
            } else {
                format!("{folder}/")
            }
        ),
    )
}
fn read_text(path: &Path) -> Result<String> {
    Ok(std::str::from_utf8(&read_bytes(path, 16 * 1024 * 1024)?)?
        .trim_start_matches('\u{feff}')
        .replace("\r\n", "\n")
        .replace('\r', "\n"))
}
fn prose(body: &str) -> &str {
    if body.starts_with('#') {
        body.splitn(3, '\n')
            .nth(2)
            .unwrap_or("")
            .trim_end_matches('\n')
    } else {
        body.trim_end_matches('\n')
    }
}
fn length(body: &str) -> usize {
    body.chars()
        .filter(|ch| !ch.is_whitespace() && !matches!(ch, '\u{1c}'..='\u{1f}'))
        .count()
}
fn as_list(value: &Value) -> Vec<Value> {
    match value {
        Value::Null => vec![],
        Value::Array(values) => values.clone(),
        value => vec![value.clone()],
    }
}
fn display(value: &Value) -> String {
    match value {
        Value::String(value) => value.trim().into(),
        Value::Null => String::new(),
        value => serde_json::to_string(value).unwrap_or_default(),
    }
}

fn data(args: &Value) -> Result<Value> {
    let mut data = match &args["data"] {
        Value::Object(data) => Value::Object(data.clone()),
        Value::String(raw) if !raw.trim().is_empty() => {
            strict_json(raw).or_else(|_| bounded_yaml(raw))?
        }
        Value::Null => json!({}),
        _ => return Err("Writer data must be an object or a JSON/YAML string object.".into()),
    };
    let values = data
        .as_object_mut()
        .ok_or("Writer data must contain an object.")?;
    for (key, value) in args
        .as_object()
        .ok_or("Writer arguments must be an object.")?
    {
        if key != "data" {
            values.entry(key.clone()).or_insert(value.clone());
        }
    }
    Ok(data)
}

fn validate(state: &Value, id: &str) -> Result<()> {
    if state["schema"] != SCHEMA || state["novel_id"] != id || !state["chapters"].is_object() {
        return Err("Invalid Writer project state; original data was preserved.".into());
    }
    for key in [
        "target_chars",
        "chapter_target_chars",
        "planned_chapters",
        "total_chars",
        "completed_chapters",
    ] {
        number(state, key, 0)?;
    }
    for (key, record) in state["chapters"].as_object().unwrap() {
        let chapter = key.parse::<u64>()?;
        if chapter == 0 || record["chapter"] != chapter {
            return Err("Writer chapter identity does not match its state key.".into());
        }
    }
    Ok(())
}

fn summaries(root: &Path, args: &Value) -> Result<Vec<Value>> {
    let directory = output(root, args)?;
    let mut result = vec![];
    if !directory.is_dir() {
        return Ok(result);
    }
    for entry in fs::read_dir(&directory)? {
        let entry = entry?;
        let id = entry
            .file_name()
            .to_str()
            .ok_or("Writer project name must be UTF-8.")?
            .to_owned();
        let project = safe_path(&directory, &id)?;
        let path = state_path(&project)?;
        if path.is_file() {
            let state = read_json(&path)?;
            validate(&state, &id)?;
            result.push(public(root, &project, &state)?);
        }
    }
    result.sort_by(|a, b| text(a, "novel_id").cmp(text(b, "novel_id")));
    Ok(result)
}

pub(super) fn infer_binding(root: &Path) -> Result<Option<Value>> {
    let items = summaries(root, &json!({}))?;
    let unfinished = items
        .iter()
        .filter(|item| item["status"] != "complete")
        .collect::<Vec<_>>();
    let active = unfinished
        .iter()
        .filter(|item| !item["active_chapter"].is_null())
        .copied()
        .collect::<Vec<_>>();
    let selected = if active.len() == 1 {
        Some(active[0])
    } else if active.is_empty() && unfinished.len() == 1 {
        Some(unfinished[0])
    } else {
        None
    };
    selected
        .map(|item| {
            binding_value(
                root,
                Path::new(text(item, "project_dir")),
                text(item, "novel_id"),
            )
        })
        .transpose()
}

pub(super) fn binding_value(root: &Path, project: &Path, id: &str) -> Result<Value> {
    Ok(
        json!({"novel_id":id,"project_dir":project.strip_prefix(root)?.to_string_lossy().replace('\\',"/")}),
    )
}

fn load_project(root: &Path, args: &Value) -> Result<(PathBuf, Value)> {
    let id = if text(args, "novel_id").is_empty() {
        let items = summaries(root, args)?;
        let unfinished = items
            .iter()
            .filter(|item| item["status"] != "complete")
            .collect::<Vec<_>>();
        let active = unfinished
            .iter()
            .filter(|item| !item["active_chapter"].is_null())
            .copied()
            .collect::<Vec<_>>();
        if active.len() == 1 {
            text(active[0], "novel_id").to_owned()
        } else if active.is_empty() && unfinished.len() == 1 {
            text(unfinished[0], "novel_id").to_owned()
        } else {
            return Err(
                "novel_id is required unless there is a single unfinished Writer project.".into(),
            );
        }
    } else {
        novel_id(text(args, "novel_id"))?
    };
    let path = safe_path(&output(root, args)?, &id)?;
    let state = read_json(&state_path(&path)?)?;
    validate(&state, &id)?;
    Ok((path, state))
}

fn ordered(state: &Value) -> Vec<&Value> {
    let mut records = state["chapters"]
        .as_object()
        .unwrap()
        .values()
        .collect::<Vec<_>>();
    records.sort_by_key(|record| record["chapter"].as_u64().unwrap_or(0));
    records
}

fn public(root: &Path, project: &Path, state: &Value) -> Result<Value> {
    let total = number(state, "total_chars", 0)?;
    let target = number(state, "target_chars", 0)?;
    let reader = safe_path(root, &format!("novel/{}", text(state, "novel_id")))?;
    Ok(
        json!({"novel_id":state["novel_id"],"title":state["title"],"status":state["status"],"configured":state["configured"],
        "project_dir":project,"reader_project_dir":reader,"reader_manuscript_path":reader.join("manuscript.txt"),
        "target_chars":target,"chapter_target_chars":state["chapter_target_chars"],"chapter_minimum_chars":state["chapter_minimum_chars"],
        "total_chars":total,"total_han_chars":state["total_han_chars"],"remaining_chars":target.saturating_sub(total),
        "planned_chapters":state["planned_chapters"],"completed_chapters":state["completed_chapters"],"active_chapter":state["active_chapter"],
        "next_chapter":next_chapter(ordered(state).last().and_then(|item|item["chapter"].as_u64()).unwrap_or(0))?,"open_threads":state["open_threads"],"active_wstyles":state["active_wstyles"],"updated_at":state["updated_at"],"native_commit_pending":commit_pending(project)?}),
    )
}

fn save(project: &Path, state: &mut Value) -> Result<()> {
    state["updated_at"] = json!(crate::session::now());
    write_json(&state_path(project)?, state)
}

fn explicit_length(text: &str) -> bool {
    let lower = text.to_lowercase();
    ["十万字","十万","100k"].iter().any(|token|lower.contains(token)) || Regex::new(r"\d+(?:\.\d+)?\s*(?:万|w|k)(?:\s*(?:字|字符|characters?))?|\d{4,6}\s*(?:字|字符|characters?)").unwrap().is_match(&lower)
}

fn bootstrap(root: &Path, args: &Value) -> Result<Value> {
    let id = novel_id(text(args, "novel_id"))?;
    let title = text(args, "title");
    let brief = text(args, "brief");
    if title.is_empty() || brief.is_empty() {
        return Err("Writer bootstrap requires title and brief.".into());
    }
    let project = safe_path(&output(root, args)?, &id)?;
    let _lock = lock(&safe_path(&project, "tracking/native.lock")?)?;
    if state_path(&project)?.exists() {
        return Err("Writer project already exists; use status or context to resume it.".into());
    }
    let mut target = number(args, "target_chars", 100000)?.max(1000);
    let combined = format!("{title}\n{brief}").to_lowercase();
    let long = [
        "小说",
        "连载",
        "长篇",
        "多章节",
        "chaptered",
        "serial",
        "novel",
    ]
    .iter()
    .any(|word| combined.contains(word));
    let short = [
        "短篇",
        "中篇",
        "单篇",
        "短文",
        "微小说",
        "one-shot",
        "oneshot",
        "novella",
    ]
    .iter()
    .any(|word| combined.contains(word));
    if long && !short && !explicit_length(&combined) {
        target = target.max(100000);
    }
    let chapter = number(args, "chapter_target_chars", 10000)?.max(500);
    let mut state = json!({"schema":SCHEMA,"novel_id":id,"title":title,"brief":brief,"status":"planning","configured":false,
        "target_chars":target,"chapter_target_chars":chapter,"planned_chapters":target.div_ceil(chapter),"total_chars":0,"total_han_chars":0,
        "completed_chapters":0,"active_chapter":null,"open_threads":[],"resolved_threads":[],"chapters":{},"created_at":crate::session::now()});
    if args.get("chapter_target_chars").is_none() || chapter == 10000 {
        state["chapter_minimum_chars"] = json!(5000);
    }
    write_bytes(&safe_path(&project,"00-project-brief.md")?,format!("# {title}\n\n## Original brief\n\n{brief}\n\n## Delivery contract\n\n- Minimum characters: {target}\n- Planned chapters: {}\n- Chapter target: {chapter}\n",target.div_ceil(chapter)).as_bytes())?;
    for (_, filename, heading) in DOCUMENTS {
        write_bytes(
            &safe_path(&project, filename)?,
            format!("# {heading}\n\n").as_bytes(),
        )?;
    }
    for (filename, heading) in [
        ("continuity", "Continuity"),
        ("timeline", "Timeline"),
        ("foreshadowing", "Foreshadowing"),
    ] {
        write_bytes(
            &safe_path(&project, &format!("tracking/{filename}.md"))?,
            format!("# {heading} Ledger\n\n").as_bytes(),
        )?;
    }
    save(&project, &mut state)?;
    object_result(public(root, &project, &state)?)
}

fn missing_documents(project: &Path) -> Result<Vec<String>> {
    let mut missing = vec![];
    for (key, file, _) in DOCUMENTS {
        let path = safe_path(project, file)?;
        if !path.is_file() || prose(&read_text(&path)?).trim().is_empty() {
            missing.push((*key).into());
        }
    }
    Ok(missing)
}

fn configure(root: &Path, project: &Path, state: &mut Value, args: &Value) -> Result<Value> {
    let data = data(args)?;
    let mut updated = vec![];
    for (key, file, heading) in DOCUMENTS {
        let body = display(&data[*key]);
        if !body.is_empty() {
            write_bytes(
                &safe_path(project, file)?,
                format!("# {heading}\n\n{body}\n").as_bytes(),
            )?;
            updated.push(*key);
        }
    }
    let missing = missing_documents(project)?;
    if updated.is_empty() && !missing.is_empty() {
        return Err(format!(
            "configure requires project documents: {}",
            missing.join(", ")
        )
        .into());
    }
    state["configured"] = json!(missing.is_empty());
    state["status"] = json!(if missing.is_empty() {
        "writing"
    } else {
        "planning"
    });
    save(project, state)?;
    let mut output = public(root, project, state)?;
    output["saved_documents"] = json!(updated);
    output["missing_documents"] = json!(missing);
    object_result(output)
}

fn delivery_minimum(state: &Value) -> u64 {
    state["chapter_minimum_chars"]
        .as_u64()
        .filter(|value| *value > 0)
        .unwrap_or_else(|| {
            state["target_chars"]
                .as_u64()
                .unwrap_or(0)
                .saturating_sub(state["total_chars"].as_u64().unwrap_or(0))
                .div_ceil(
                    state["planned_chapters"]
                        .as_u64()
                        .unwrap_or(0)
                        .saturating_sub(state["completed_chapters"].as_u64().unwrap_or(0))
                        .max(1),
                )
        })
}

fn prepare(
    root: &Path,
    project: &Path,
    state: &mut Value,
    args: &Value,
    wstyle: &Value,
) -> Result<Value> {
    if state["configured"] != true || !missing_documents(project)?.is_empty() {
        return Err("Configure all five Writer bibles before preparing a chapter.".into());
    }
    if state["status"] == "complete"
        || (number(state, "total_chars", 0)? >= number(state, "target_chars", 0)?
            && number(state, "completed_chapters", 0)? >= number(state, "planned_chapters", 0)?)
    {
        return Err(
            "The Writer delivery target is met; run audit before opening more chapters.".into(),
        );
    }
    let chapter = number(
        args,
        "chapter",
        next_chapter(number(state, "completed_chapters", 0)?)?,
    )?;
    if chapter == 0 {
        return Err("Writer chapter must be positive.".into());
    }
    next_chapter(chapter)?;
    if let Some(active) = state["active_chapter"].as_u64()
        && active != chapter
        && !state["chapters"]
            .as_object()
            .unwrap()
            .contains_key(&active.to_string())
    {
        return Err(format!(
            "Chapter {active} is prepared but uncommitted; finish or reprepare it first."
        )
        .into());
    }
    let data = data(args)?;
    let outline = display(&data["outline"]);
    let title = if !text(args, "title").is_empty() {
        text(args, "title").to_owned()
    } else if !text(&data, "title").is_empty() {
        text(&data, "title").into()
    } else {
        outline
            .lines()
            .find(|line| !line.trim().is_empty())
            .unwrap_or("")
            .trim_start_matches('#')
            .trim()
            .chars()
            .take(100)
            .collect()
    };
    if title.is_empty() || outline.is_empty() {
        return Err("Writer prepare_chapter requires title and data.outline.".into());
    }
    let target = number(
        &data,
        "target_chars",
        number(state, "chapter_target_chars", 10000)?,
    )?
    .max(number(state, "chapter_target_chars", 10000)?)
    .max(500);
    let minimum = number(state, "chapter_minimum_chars", scaled_chars(target, 70)?)?
        .max(delivery_minimum(state))
        .max(350);
    let mut card = json!({"chapter":chapter,"title":title,"outline":outline,"target_chars":target,"minimum_chars_to_commit":minimum,
        "recommended_draft_chars":minimum.max(scaled_chars(minimum,115)?).max(if state.get("chapter_minimum_chars").is_some(){target}else{0}),"wstyle":wstyle,"prepared_at":crate::session::now()});
    for key in [
        "scene_beats",
        "continuity_requirements",
        "relationship_progression",
    ] {
        card[key] = json!(as_list(&data[key]));
    }
    for key in ["opening_hook", "ending_hook"] {
        card[key] = json!(display(&data[key]));
    }
    let intent = serde_json::Map::from_iter(
        [
            "narrative_function",
            "character_goal",
            "causal_change",
            "emotional_change",
            "reader_expectation",
        ]
        .iter()
        .filter(|key| !display(&data[**key]).is_empty())
        .map(|key| ((*key).into(), json!(display(&data[*key])))),
    );
    if !intent.is_empty() {
        card["quality_intent"] = json!(intent);
    }
    quality::validate_control(&card)?;
    let pending = artifact(project, "drafts", chapter, "json")?;
    let previous = artifact(project, "control-cards", chapter, "json")?;
    if pending.is_file() && read_json(&pending)?["requires_reprepare"] == true && previous.is_file()
    {
        let fingerprint = |value: &Value| {
            let mut value = value.clone();
            value.as_object_mut().unwrap().remove("prepared_at");
            value.as_object_mut().unwrap().remove("wstyle");
            value
        };
        if fingerprint(&read_json(&previous)?) == fingerprint(&card) {
            return Err("The exhausted chapter requires a materially revised outline/control card; identical reprepare cannot reset its repair limit.".into());
        }
    }
    write_json(&artifact(project, "control-cards", chapter, "json")?, &card)?;
    archive_pending(project, chapter, true)?;
    state["active_chapter"] = json!(chapter);
    state["status"] = json!("writing");
    save(project, state)?;
    object_result(context(root, project, state, chapter, Some(card))?)
}

fn archive_pending(project: &Path, chapter: u64, remove: bool) -> Result<()> {
    let path = artifact(project, "drafts", chapter, "json")?;
    if path.is_file() {
        let bytes = read_bytes(&path, 16 * 1024 * 1024)?;
        write_bytes(
            &safe_path(
                project,
                &format!(
                    "drafts/revisions/chapter-{chapter:04}-{}.json",
                    digest(&bytes)
                ),
            )?,
            &bytes,
        )?;
        if remove {
            fs::remove_file(&path)?;
        }
    }
    Ok(())
}

fn context(
    root: &Path,
    project: &Path,
    state: &Value,
    chapter: u64,
    card: Option<Value>,
) -> Result<Value> {
    let mut bibles = serde_json::Map::new();
    for (_, file, _) in DOCUMENTS.iter().take(4) {
        let path = safe_path(project, file)?;
        bibles.insert(
            (*file).into(),
            json!(if path.is_file() {
                read_text(&path)?.chars().take(4000).collect::<String>()
            } else {
                String::new()
            }),
        );
    }
    let pending = artifact(project, "drafts", chapter, "json")?;
    let chapter_path = artifact(project, "chapters", chapter, "md")?;
    let current = if pending.is_file() {
        text(&read_json(&pending)?["data"], "content").to_owned()
    } else if chapter_path.is_file() {
        prose(&read_text(&chapter_path)?).to_owned()
    } else {
        String::new()
    };
    let pending = if pending.is_file() {
        let mut data = read_json(&pending)?;
        let body = text(&data["data"], "content");
        data["content_tail"] = json!(
            body.chars()
                .rev()
                .take(1600)
                .collect::<Vec<_>>()
                .into_iter()
                .rev()
                .collect::<String>()
        );
        data.as_object_mut().unwrap().remove("data");
        Some(data)
    } else {
        None
    };
    let recent = ordered(state)
        .into_iter()
        .rev()
        .take(3)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .cloned()
        .collect::<Vec<_>>();
    let minimum = card
        .as_ref()
        .and_then(|card| card["minimum_chars_to_commit"].as_u64())
        .unwrap_or(0)
        .max(delivery_minimum(state));
    Ok(
        json!({"project":public(root,project,state)?,"chapter":chapter,"control_card":card,"pending_draft":pending,
        "minimum_chars_to_commit":minimum,"recommended_draft_chars":scaled_chars(minimum,115)?,"recent_chapters":recent,"open_threads":state["open_threads"],"bibles":bibles,"editorial_review":wstyle::latest_review(project,chapter,&current)?}),
    )
}

fn normalize_heading(body: &str, title: &str, chapter: u64) -> String {
    let mut lines = body.lines();
    let first = lines.next().unwrap_or("");
    let heading = first.trim().trim_start_matches('#').trim();
    let chapter_heading=Regex::new(&format!(r"(?i)^(?:chapter\s*{chapter}|第\s*(?:{chapter}|[一二三四五六七八九十百千零〇两]+)\s*[章节回])[ :：.、\-–—]*(?:{})?$",regex::escape(title))).unwrap();
    if heading == title || chapter_heading.is_match(heading) {
        lines.collect::<Vec<_>>().join("\n").trim().into()
    } else {
        body.trim().into()
    }
}

fn prior_prose(project: &Path, state: &Value, exclude: u64) -> Result<String> {
    let mut result = String::new();
    for record in ordered(state) {
        if number(record, "chapter", 0)? != exclude {
            let path = safe_path(project, text(record, "path"))?;
            result.push_str(prose(&read_text(&path)?));
            result.push('\n');
        }
    }
    Ok(result)
}

pub(super) fn mechanical_report(
    project: &Path,
    state: &Value,
    chapter: u64,
    content: &str,
    control: &Value,
) -> Result<Value> {
    quality::report(
        content,
        number(
            control,
            "target_chars",
            number(state, "chapter_target_chars", 500)?,
        )?,
        0,
        number(state, "chapter_minimum_chars", 0)?,
        &prior_prose(project, state, chapter)?,
    )
}

fn merge_append(prior: &str, append: &str) -> String {
    let paragraphs = Regex::new(r"\n\s*\n+").unwrap();
    let old = paragraphs
        .split(prior.trim())
        .map(str::trim)
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>();
    let new = paragraphs
        .split(append.trim())
        .map(str::trim)
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>();
    let normalized = |value: &str| {
        value
            .chars()
            .filter(|ch| {
                !ch.is_whitespace()
                    && !"\"'“”‘’`，,。；;：:、-—_()（）《》<>【】[]的是在".contains(*ch)
            })
            .collect::<String>()
    };
    let a = old.iter().map(|part| normalized(part)).collect::<Vec<_>>();
    let b = new.iter().map(|part| normalized(part)).collect::<Vec<_>>();
    let mut skip = 0;
    for overlap in (1..=a.len().min(b.len()).min(24)).rev() {
        if a[a.len() - overlap..] == b[..overlap] {
            skip = overlap;
            break;
        }
    }
    while skip < b.len() && a.iter().rev().take(24).any(|value| *value == b[skip]) {
        skip += 1;
    }
    new[skip..].join("\n\n")
}

fn refresh_totals(state: &mut Value) -> Result<()> {
    let records = ordered(state);
    let mut chars = 0u64;
    let mut han = 0u64;
    let mut opened = vec![];
    let mut resolved = vec![];
    for record in &records {
        chars = chars
            .checked_add(number(record, "chars", 0)?)
            .ok_or("Writer character total overflow.")?;
        han = han
            .checked_add(number(record, "han_chars", 0)?)
            .ok_or("Writer Han total overflow.")?;
        for item in as_list(&record["opened_threads"]) {
            let item = display(&item);
            if !opened.contains(&item) {
                opened.push(item);
            }
        }
        for item in as_list(&record["resolved_threads"]) {
            let item = display(&item);
            if !resolved.contains(&item) {
                resolved.push(item);
            }
        }
    }
    let count = records.len();
    opened.retain(|item| !resolved.contains(item));
    state["total_chars"] = json!(chars);
    state["total_han_chars"] = json!(han);
    state["completed_chapters"] = json!(count);
    state["open_threads"] = json!(opened);
    state["resolved_threads"] = json!(resolved);
    Ok(())
}

fn replace_ledger(path: &Path, chapter: u64, section: &str) -> Result<()> {
    let mut existing = if path.is_file() {
        read_text(path)?
    } else {
        format!("# {}\n\n", path.file_stem().unwrap().to_string_lossy())
    };
    let marker = format!("## Chapter {chapter}:");
    if let Some(start) = existing.find(&marker) {
        let end = existing[start + marker.len()..]
            .find("\n## Chapter ")
            .map(|offset| start + marker.len() + offset + 1)
            .unwrap_or(existing.len());
        existing.replace_range(start..end, "");
    }
    write_bytes(
        path,
        format!("{}\n\n{}\n", existing.trim_end(), section.trim_end()).as_bytes(),
    )
}

fn ledgers(project: &Path, record: &Value) -> Result<()> {
    let chapter = number(record, "chapter", 0)?;
    let heading = format!("## Chapter {chapter}: {}\n\n", text(record, "title"));
    let mut continuity = format!("{heading}{}\n", text(record, "summary"));
    for (label, key) in [
        ("Key events", "key_events"),
        ("Character changes", "character_updates"),
        ("Relationship changes", "relationship_updates"),
    ] {
        if !as_list(&record[key]).is_empty() {
            continuity.push_str(&format!("\n### {label}\n"));
            for item in as_list(&record[key]) {
                continuity.push_str(&format!("- {}\n", display(&item)));
            }
        }
    }
    replace_ledger(
        &safe_path(project, "tracking/continuity.md")?,
        chapter,
        &continuity,
    )?;
    let mut timeline = heading.clone();
    for item in as_list(&record["timeline_updates"]) {
        timeline.push_str(&format!("- {}\n", display(&item)));
    }
    replace_ledger(
        &safe_path(project, "tracking/timeline.md")?,
        chapter,
        &timeline,
    )?;
    let mut foreshadowing = heading;
    for (label, key) in [
        ("Opened", "foreshadowing_opened"),
        ("Resolved", "foreshadowing_resolved"),
    ] {
        for item in as_list(&record[key]) {
            foreshadowing.push_str(&format!("- {label}: {}\n", display(&item)));
        }
    }
    replace_ledger(
        &safe_path(project, "tracking/foreshadowing.md")?,
        chapter,
        &foreshadowing,
    )
}

fn reader_chapter(chapter: u64, title: &str, body: &str) -> String {
    format!("Chapter {chapter}: {title}\n\n{}\n", body.trim_end())
}
fn reader_manuscript(title: &str, chapters: &[String]) -> String {
    let mut parts = vec![title.trim().to_owned(), String::new()];
    parts.extend(chapters.iter().map(|part| part.trim_end().to_owned()));
    format!("{}\n", parts.join("\n\n").trim_end())
}

fn exports(root: &Path, project: &Path, state: &Value) -> Result<()> {
    let directory = safe_path(root, &format!("novel/{}", text(state, "novel_id")))?;
    let mut rendered = vec![];
    for record in ordered(state) {
        let chapter = number(record, "chapter", 0)?;
        let body = read_text(&safe_path(project, text(record, "path"))?)?;
        let text = reader_chapter(chapter, text(record, "title"), prose(&body));
        write_bytes(&artifact(&directory, "", chapter, "txt")?, text.as_bytes())?;
        rendered.push(text);
    }
    if !rendered.is_empty() {
        write_bytes(
            &safe_path(&directory, "manuscript.txt")?,
            reader_manuscript(text(state, "title"), &rendered).as_bytes(),
        )?;
    }
    Ok(())
}

fn commit(
    root: &Path,
    project: &Path,
    state: &mut Value,
    args: &Value,
    wstyle: &Value,
) -> Result<Value> {
    if state["status"] == "complete" {
        return Err("Writer project is complete; a new chapter requires an explicit new project or revision.".into());
    }
    let chapter = number(args, "chapter", number(state, "active_chapter", 0)?)?;
    if chapter == 0 {
        return Err("commit_chapter requires a prepared chapter.".into());
    }
    next_chapter(chapter)?;
    let card = read_json(&artifact(project, "control-cards", chapter, "json")?)?;
    let mut data = data(args)?;
    let pending_path = artifact(project, "drafts", chapter, "json")?;
    let pending = if pending_path.is_file() {
        Some(read_json(&pending_path)?)
    } else {
        None
    };
    if pending
        .as_ref()
        .is_some_and(|pending| pending["requires_reprepare"] == true)
    {
        return Err("Three Writer repair attempts were exhausted; materially reprepare the control card before committing again. The full rejected draft was preserved.".into());
    }
    let mut segments = vec![];
    if !text(&data, "append_content").is_empty() {
        let old = pending
            .as_ref()
            .ok_or("append_content requires a preserved rejected draft.")?;
        if old["recovery_mode"] != "append_only" {
            return Err("This draft requires a full revised chapter; append_content is only for a length-only rejection.".into());
        }
        let prior = text(&old["data"], "content");
        let append = merge_append(prior, text(&data, "append_content"));
        if append.is_empty() {
            return Err(
                "Append retry repeated the preserved tail; continue from the first unseen beat."
                    .into(),
            );
        }
        let mut merged = old["data"].clone();
        for (key, value) in data.as_object().unwrap() {
            if key != "append_content" && !value.is_null() {
                merged[key] = value.clone();
            }
        }
        merged["content"] = json!(format!("{prior}\n\n{append}"));
        data = merged;
        segments = old["wstyle_segments"]
            .as_array()
            .cloned()
            .unwrap_or_default();
        segments.push(json!({"start":prior.chars().count()+2,"end":text(&data,"content").chars().count(),"wstyle":wstyle}));
    }
    let title = if !text(args, "title").is_empty() {
        text(args, "title")
    } else if !text(&data, "title").is_empty() {
        text(&data, "title")
    } else {
        text(&card, "title")
    }
    .to_owned();
    let content = normalize_heading(text(&data, "content"), &title, chapter);
    if content.is_empty() || title.is_empty() {
        return Err("Writer commit requires a complete title and data.content.".into());
    }
    if segments.is_empty() {
        segments.push(json!({"start":0,"end":content.chars().count(),"wstyle":wstyle}));
    }
    let quality = quality::report(
        &content,
        number(
            &card,
            "target_chars",
            number(state, "chapter_target_chars", 10000)?,
        )?,
        delivery_minimum(state),
        number(state, "chapter_minimum_chars", 0)?,
        &prior_prose(project, state, chapter)?,
    )?;
    if quality["passed"] != true {
        let retries = pending
            .as_ref()
            .and_then(|item| item["quality_retry_count"].as_u64())
            .unwrap_or(0)
            .checked_add(1)
            .ok_or("Writer repair count exceeds the supported integer range.")?;
        let exhausted = retries >= 3;
        let shortage =
            number(&quality, "minimum_chars", 0)?.saturating_sub(number(&quality, "chars", 0)?);
        let only_length = shortage > 0 && quality["blocking_issues"].as_array().unwrap().len() == 1;
        data["content"] = json!(content);
        archive_pending(project, chapter, false)?;
        let recommended = if only_length {
            shortage.saturating_add(120u64.max(number(&quality, "minimum_chars", 0)?.div_ceil(10)))
        } else {
            0
        };
        write_json(
            &pending_path,
            &json!({"chapter":chapter,"title":title,"data":data,"quality":quality,"recommended_append_chars":recommended,
            "quality_retry_count":retries,"max_quality_retry_attempts":3,"blocking_issues":quality["blocking_issues"],"recovery_mode":if exhausted{"reprepare"}else if only_length{"append_only"}else{"full_rewrite"},"requires_reprepare":exhausted,"wstyle_segments":segments,"saved_at":crate::session::now()}),
        )?;
        return Err(format!("Writer chapter {chapter} failed deterministic gates ({retries}/3): {}. Full rejected prose is preserved. {}",quality["blocking_issues"],if exhausted{"Materially reprepare the control card before another commit.".to_owned()}else if only_length{format!("Continue from the first unseen beat using data.append_content, recommended at least {recommended} new non-whitespace characters; every gate runs again.")}else{"Revise the full data.content; append-only is unavailable for this failure.".into()}).into());
    }
    let path = artifact(project, "chapters", chapter, "md")?;
    let chapter_text = format!("# Chapter {chapter}: {title}\n\n{content}\n");
    if path.is_file() {
        let original = read_bytes(&path, 16 * 1024 * 1024)?;
        if original != chapter_text.as_bytes() {
            let revision = safe_path(
                project,
                &format!(
                    "chapters/revisions/chapter-{chapter:04}-{}.md",
                    digest(&original)
                ),
            )?;
            write_bytes(&revision, &original)?;
            if let Some(previous) = state["chapters"].get(chapter.to_string()) {
                write_json(&revision.with_extension("json"), previous)?;
            }
        }
    }
    let supplied = text(&data, "summary");
    let summary = if supplied.is_empty() {
        content
            .split_terminator(['。', '！', '？', '.', '!', '?'])
            .take(2)
            .collect::<Vec<_>>()
            .join("。")
            .chars()
            .take(320)
            .collect::<String>()
    } else {
        supplied.into()
    };
    let mut record = json!({"chapter":chapter,"title":title,"path":format!("chapters/chapter-{chapter:04}.md"),"chars":quality["chars"],"han_chars":quality["han_chars"],"sha256":digest(chapter_text.as_bytes()),"summary":summary,"summary_source":if supplied.is_empty(){"extractive_fallback"}else{"model"},"quality":quality,"wstyle_segments":segments,"committed_at":crate::session::now()});
    for key in [
        "key_events",
        "character_updates",
        "relationship_updates",
        "timeline_updates",
        "opened_threads",
        "advanced_threads",
        "resolved_threads",
        "foreshadowing_opened",
        "foreshadowing_resolved",
    ] {
        record[key] = json!(as_list(&data[key]));
    }
    state["chapters"][chapter.to_string()] = record.clone();
    refresh_totals(state)?;
    state["active_chapter"] = Value::Null;
    state["updated_at"] = json!(crate::session::now());
    let mut after = serde_json::to_vec_pretty(state)?;
    after.push(b'\n');
    write_json(
        &safe_path(project, "tracking/native-commit.json")?,
        &json!({"schema":"reverie.writer.native-commit.v1","status":"prepared", "chapter":chapter,
        "chapter_text":chapter_text,"next_state":state,"state_before_sha256":digest(&read_bytes(&state_path(project)?,16*1024*1024)?),"state_after_sha256":digest(&after)}),
    )?;
    resume_commit(root, project)?;
    object_result(json!({"chapter":record,"project":public(root,project,state)?}))
}

fn commit_pending(project: &Path) -> Result<bool> {
    let path = safe_path(project, "tracking/native-commit.json")?;
    Ok(path.is_file() && read_json(&path)?["status"] == "prepared")
}

fn resume_commit(root: &Path, project: &Path) -> Result<()> {
    let path = safe_path(project, "tracking/native-commit.json")?;
    if !path.is_file() {
        return Ok(());
    }
    let mut journal = read_json(&path)?;
    if journal["status"] != "prepared" {
        return Ok(());
    }
    if journal["schema"] != "reverie.writer.native-commit.v1" {
        return Err("Unknown Writer commit journal; source state was preserved.".into());
    }
    let mut after = serde_json::to_vec_pretty(&journal["next_state"])?;
    after.push(b'\n');
    if digest(&after) != text(&journal, "state_after_sha256") {
        return Err(
            "Writer commit journal failed content validation; source state was preserved.".into(),
        );
    }
    let existing = digest(&read_bytes(&state_path(project)?, 16 * 1024 * 1024)?);
    if existing != text(&journal, "state_before_sha256")
        && existing != text(&journal, "state_after_sha256")
    {
        return Err("Writer state changed outside the pending commit; inspect its preserved journal before recovery.".into());
    }
    let state = &journal["next_state"];
    validate(state, project.file_name().unwrap().to_str().unwrap_or(""))?;
    let chapter = number(&journal, "chapter", 0)?;
    let record = &state["chapters"][chapter.to_string()];
    let chapter_text = journal["chapter_text"]
        .as_str()
        .ok_or("Writer journal has no complete chapter text.")?;
    if digest(chapter_text.as_bytes()) != text(record, "sha256") {
        return Err(
            "Writer journal chapter identity is invalid; original data was preserved.".into(),
        );
    }
    for other in ordered(state) {
        if number(other, "chapter", 0)? != chapter {
            let bytes = read_bytes(&safe_path(project, text(other, "path"))?, 16 * 1024 * 1024)?;
            if digest(&bytes) != text(other, "sha256") {
                return Err("An earlier Writer chapter changed; inspect it before recovering the pending commit.".into());
            }
        }
    }
    write_bytes(
        &artifact(project, "chapters", chapter, "md")?,
        chapter_text.as_bytes(),
    )?;
    ledgers(project, record)?;
    exports(root, project, state)?;
    write_json(&state_path(project)?, state)?;
    archive_pending(project, chapter, true)?;
    journal["status"] = json!("completed");
    write_json(&path, &journal)
}

fn audit(root: &Path, project: &Path, state: &Value) -> Result<Value> {
    let mut mismatches = vec![];
    let mut numbers = vec![];
    let mut total = 0u64;
    let mut rendered = vec![];
    let reader = safe_path(root, &format!("novel/{}", text(state, "novel_id")))?;
    for record in ordered(state) {
        let chapter = number(record, "chapter", 0)?;
        let path = safe_path(project, text(record, "path"))?;
        if !path.is_file() {
            mismatches.push(format!("Chapter {chapter} file is missing."));
            continue;
        }
        let bytes = read_bytes(&path, 16 * 1024 * 1024)?;
        let body = std::str::from_utf8(&bytes)?;
        let chars = length(prose(body)) as u64;
        if digest(&bytes) != text(record, "sha256") {
            mismatches.push(format!("Chapter {chapter} bytes changed after commit."));
        }
        if chars != number(record, "chars", 0)? {
            mismatches.push(format!(
                "Chapter {chapter} character count differs from state."
            ));
        }
        let expected = reader_chapter(chapter, text(record, "title"), prose(body));
        let export = artifact(&reader, "", chapter, "txt")?;
        if !export.is_file() || read_bytes(&export, 16 * 1024 * 1024)? != expected.as_bytes() {
            mismatches.push(format!(
                "Reader export for chapter {chapter} differs from committed prose."
            ));
        }
        total = total
            .checked_add(chars)
            .ok_or("Writer disk total overflow.")?;
        numbers.push(chapter);
        rendered.push(expected);
    }
    if let Some(last) = numbers.last()
        && (numbers.len() as u64 != *last
            || numbers.first() != Some(&1)
            || numbers
                .windows(2)
                .any(|pair| Some(pair[1]) != pair[0].checked_add(1)))
    {
        mismatches.push("Committed Writer chapter numbers are not consecutive from 1.".into());
    }
    let manuscript = safe_path(&reader, "manuscript.txt")?;
    if !rendered.is_empty()
        && (!manuscript.is_file()
            || read_bytes(&manuscript, 64 * 1024 * 1024)?
                != reader_manuscript(text(state, "title"), &rendered).as_bytes())
    {
        mismatches.push("Merged reader manuscript differs from committed prose.".into());
    }
    let mut blockers = mismatches.clone();
    if state["configured"] != true || !missing_documents(project)?.is_empty() {
        blockers.push("All five project bibles must be configured.".into());
    }
    if commit_pending(project)? {
        blockers.push("A preserved native commit awaits recovery; the next authorized Writer write resumes it after validation.".into());
    }
    if total < number(state, "target_chars", 0)? {
        blockers.push(format!(
            "Verified total is {total}/{} non-whitespace characters.",
            number(state, "target_chars", 0)?
        ));
    }
    let overrun = state["active_chapter"].as_u64().filter(|chapter| {
        total >= state["target_chars"].as_u64().unwrap_or(0)
            && *chapter > numbers.last().copied().unwrap_or(0)
    });
    if !state["active_chapter"].is_null() && overrun.is_none() {
        blockers.push(format!(
            "Chapter {} is prepared but uncommitted.",
            state["active_chapter"]
        ));
    }
    Ok(
        json!({"novel_id":state["novel_id"],"title":state["title"],"status":state["status"],"project_dir":project,"reader_project_dir":reader,"reader_manuscript_path":manuscript,
        "target_chars":state["target_chars"],"disk_total_chars":total,"disk_chapter_count":numbers.len(),"state_total_chars":state["total_chars"],"mismatches":mismatches,
        "blocking_issues":blockers,"ignored_overrun_control_card":overrun,"completion_ready":blockers.is_empty()}),
    )
}

pub(super) fn execute(args: &Value, root: &Path, wstyle: &Value) -> Result<Value> {
    let action = text(args, "action");
    if action == "bootstrap" {
        return bootstrap(root, args);
    }
    if action == "list_projects" {
        return object_result(json!({"projects":summaries(root,args)?}));
    }
    if action == "status" && text(args, "novel_id").is_empty() && infer_binding(root)?.is_none() {
        return object_result(json!({"projects":summaries(root,args)?}));
    }
    let (project, _) = load_project(root, args)?;
    let _lock = lock(&safe_path(&project, "tracking/native.lock")?)?;
    if ["configure", "prepare_chapter", "commit_chapter", "complete"].contains(&action) {
        resume_commit(root, &project)?;
    }
    let mut state = read_json(&state_path(&project)?)?;
    validate(
        &state,
        project
            .file_name()
            .unwrap()
            .to_str()
            .ok_or("Writer project filename is not UTF-8.")?,
    )?;
    match action {
        "configure" => configure(root, &project, &mut state, args),
        "prepare_chapter" => prepare(root, &project, &mut state, args, wstyle),
        "commit_chapter" => commit(root, &project, &mut state, args, wstyle),
        "context" => {
            let chapter = number(
                args,
                "chapter",
                number(
                    &state,
                    "active_chapter",
                    next_chapter(number(&state, "completed_chapters", 0)?)?,
                )?,
            )?;
            let path = artifact(&project, "control-cards", chapter, "json")?;
            let card = if path.is_file() {
                Some(read_json(&path)?)
            } else {
                None
            };
            object_result(context(root, &project, &state, chapter, card)?)
        }
        "status" => object_result(public(root, &project, &state)?),
        "audit" => object_result(audit(root, &project, &state)?),
        "complete" => {
            let mut result = audit(root, &project, &state)?;
            if result["completion_ready"] != true {
                return Err(format!(
                    "Writer completion gates remain: {}",
                    result["blocking_issues"]
                )
                .into());
            }
            if state["status"] != "complete" {
                state["status"] = json!("complete");
                state["active_chapter"] = Value::Null;
                state["completed_at"] = json!(crate::session::now());
                save(&project, &mut state)?;
            }
            result["status"] = json!("complete");
            object_result(result)
        }
        _ => Err("Unknown serial_novel action.".into()),
    }
}

pub(super) fn guidance(root: &Path) -> Result<String> {
    Ok(format!(
        "## Writer persistent long-form fiction\nUse serial_novel for the entire native fiction project. Preserve the original brief, five bibles, control cards, complete prose, failed drafts, continuity and readable exports. Inspect status/context before resuming. Configure all five bibles before preparing a chapter. Draft actual complete chapters; avoid filler, placeholders, repeated passages and fabricated quality claims. Honor chapter minima and the total delivery contract. A length-only rejection preserves the draft for append_content; other failures require revised full prose. After three failed repairs materially reprepare the chapter. Use audit/complete against actual disk bytes and reader exports before claiming delivery. General file editors and shell execution are unavailable in Writer; arbitrary file writing belongs to Reverie mode. Deterministic gates measure text checks, not literary quality. Current projects: {}",
        serde_json::to_string(&summaries(root, &json!({}))?)?
    ))
}

pub(super) fn definition() -> Value {
    let mut definition = json!({"type":"function","function":{"name":"serial_novel","description":"Persist a complete native Writer project, five bibles, chapter control cards, full prose, rejected drafts, continuity, reader exports and completion audits.","parameters":{"type":"object","properties":{
        "action":{"type":"string","enum":["bootstrap","configure","prepare_chapter","commit_chapter","context","status","audit","complete","list_projects"]},"novel_id":{"type":"string"},"title":{"type":"string"},"brief":{"type":"string"},"target_chars":{"type":"integer","minimum":1000,"default":100000},"chapter_target_chars":{"type":"integer","minimum":500,"default":10000},"chapter":{"type":"integer","minimum":1},"output_dir":{"type":"string","default":"novels"},"data":{"type":"object","properties":{"content":{"type":"string"},"append_content":{"type":"string"},"summary":{"type":"string"},"outline":{"type":"string"},"target_chars":{"type":"integer"},"world_bible":{"type":"string"},"cast_bible":{"type":"string"},"story_architecture":{"type":"string"},"style_guide":{"type":"string"},"roadmap":{"type":"string"},"scene_beats":{"type":"array","items":{"type":"string"}},"continuity_requirements":{"type":"array","items":{"type":"string"}},"relationship_progression":{"type":"array","items":{"type":"string"}},"opening_hook":{"type":"string"},"ending_hook":{"type":"string"}}}},"required":["action"]}}});
    let properties = definition["function"]["parameters"]["properties"]["data"]["properties"]
        .as_object_mut()
        .unwrap();
    for key in [
        "key_events",
        "character_updates",
        "relationship_updates",
        "timeline_updates",
        "opened_threads",
        "advanced_threads",
        "resolved_threads",
        "foreshadowing_opened",
        "foreshadowing_resolved",
    ] {
        properties.insert(key.into(), json!({"type":"array","items":{},"description":"Explicit chapter continuity facts or thread changes retained with the complete original prose."}));
    }
    for key in [
        "narrative_function",
        "character_goal",
        "causal_change",
        "emotional_change",
        "reader_expectation",
    ] {
        properties.insert(key.into(), json!({"type":"string","description":"Concrete chapter intent recorded in the control card before drafting."}));
    }
    definition
}

#[cfg(test)]
mod tests {
    use super::*;
    fn configured(root: &Path) -> (PathBuf, Value) {
        bootstrap(root,&json!({"novel_id":"novel","title":"Fixture","brief":"Explicit 1000 characters short story","target_chars":1000,"chapter_target_chars":1000})).unwrap();
        let (project, mut state) = load_project(root, &json!({"novel_id":"novel"})).unwrap();
        let data = serde_json::Map::from_iter(DOCUMENTS.iter().map(|(key, _, _)| {
            (
                (*key).into(),
                json!("Concrete original facts and constraints."),
            )
        }));
        configure(root, &project, &mut state, &json!({"data":data})).unwrap();
        (project, state)
    }
    #[test]
    fn very_large_length_and_chapter_inputs_preserve_prose_without_integer_wrap() {
        let root = tempfile::tempdir().unwrap();
        let p = root.path();
        let (project, mut state) = configured(p);
        prepare(p, &project, &mut state, &json!({"title":"Start","data":{"outline":"A concrete original action","target_chars":u64::MAX}}), &json!({})).unwrap();
        let card = artifact(&project, "control-cards", 1, "json").unwrap();
        assert!(
            read_json(&card).unwrap()["minimum_chars_to_commit"]
                .as_u64()
                .unwrap()
                > u64::MAX / 2
        );
        assert!(execute(&json!({"action":"commit_chapter","novel_id":"novel","data":{"content":"完整的短篇原文。"}}), p, &json!({})).is_err());
        let draft = read_json(&artifact(&project, "drafts", 1, "json").unwrap()).unwrap();
        assert_eq!(draft["data"]["content"], "完整的短篇原文。");
        assert!(draft["quality"]["minimum_chars"].as_u64().unwrap() > u64::MAX / 2);
        let before = fs::read(&card).unwrap();
        assert!(prepare(p, &project, &mut state, &json!({"chapter":u64::MAX,"title":"Invalid","data":{"outline":"Invalid numeric chapter"}}), &json!({})).is_err());
        state["chapter_minimum_chars"] = json!(u64::MAX);
        assert!(prepare(p, &project, &mut state, &json!({"title":"Invalid recommendation","data":{"outline":"A concrete original action"}}), &json!({})).is_err());
        assert_eq!(fs::read(&card).unwrap(), before);
    }

    #[test]
    fn five_bibles_control_cards_and_saved_binding() {
        let root = tempfile::tempdir().unwrap();
        let p = root.path();
        bootstrap(
            p,
            &json!({"novel_id":"novel","title":"Fixture","brief":"A novel"}),
        )
        .unwrap();
        let (project, mut state) = load_project(p, &json!({"novel_id":"novel"})).unwrap();
        assert_eq!(state["target_chars"], 100000);
        assert_eq!(state["chapter_minimum_chars"], 5000);
        assert!(
            prepare(
                p,
                &project,
                &mut state,
                &json!({"title":"Start","data":{"outline":"Original plan"}}),
                &json!({})
            )
            .is_err()
        );
        let data = serde_json::Map::from_iter(
            DOCUMENTS
                .iter()
                .map(|(key, _, _)| ((*key).into(), json!("Original bible body"))),
        );
        configure(p, &project, &mut state, &json!({"data":data})).unwrap();
        let result = prepare(
            p,
            &project,
            &mut state,
            &json!({"title":"Start","data":{"outline":"Original plan"}}),
            &json!({"cards":[]}),
        )
        .unwrap();
        assert_eq!(result["data"]["minimum_chars_to_commit"], 5000);
        assert_eq!(infer_binding(p).unwrap().unwrap()["novel_id"], "novel");
        assert!(prepare(p,&project,&mut state,&json!({"chapter":2,"title":"Skip","data":{"outline":"Cannot skip prepared chapter"}}),&json!({})).is_err());
    }

    #[test]
    fn rejected_prose_append_recovery_export_audit_and_original_revision() {
        let root = tempfile::tempdir().unwrap();
        let p = root.path();
        let (project, mut state) = configured(p);
        prepare(
            p,
            &project,
            &mut state,
            &json!({"title":"Start","data":{"outline":"Complete original action"}}),
            &json!({"cards":[]}),
        )
        .unwrap();
        let short = (0..12)
            .map(|n| format!("{n} 从门口走到河岸，角色作出属于自己的决定。\n"))
            .collect::<String>();
        assert!(
            execute(
                &json!({"action":"commit_chapter","novel_id":"novel","data":{"content":short}}),
                p,
                &json!({"cards":[]})
            )
            .is_err()
        );
        let pending = read_json(&artifact(&project, "drafts", 1, "json").unwrap()).unwrap();
        assert_eq!(pending["data"]["content"], short.trim());
        assert_eq!(pending["recovery_mode"], "append_only");
        let append = (12..100)
            .map(|n| format!("{n} 她拿回自己的行李，然后踏入新的车站继续路程。\n"))
            .collect::<String>();
        execute(&json!({"action":"commit_chapter","novel_id":"novel","data":{"append_content":append,"summary":"Original summary","opened_threads":["A"],"timeline_updates":["Day one"]}}),p,&json!({"cards":[]})).unwrap();
        let (_, state) = load_project(p, &json!({"novel_id":"novel"})).unwrap();
        assert_eq!(state["completed_chapters"], 1);
        assert_eq!(state["open_threads"], json!(["A"]));
        assert_eq!(
            audit(p, &project, &state).unwrap()["completion_ready"],
            true
        );
        let original = fs::read(artifact(&project, "chapters", 1, "md").unwrap()).unwrap();
        assert!(
            String::from_utf8(original.clone())
                .unwrap()
                .contains(short.trim())
        );
        let revised = (0..100)
            .map(|n| format!("{n} 另一次旅途里，她选择把钥匙交还给站长。\n"))
            .collect::<String>();
        execute(&json!({"action":"commit_chapter","novel_id":"novel","chapter":1,"data":{"content":revised}}),p,&json!({"cards":[]})).unwrap();
        assert_eq!(
            fs::read(
                safe_path(
                    &project,
                    &format!("chapters/revisions/chapter-0001-{}.md", digest(&original))
                )
                .unwrap()
            )
            .unwrap(),
            original
        );
        execute(
            &json!({"action":"complete","novel_id":"novel"}),
            p,
            &json!({}),
        )
        .unwrap();
        fs::write(
            artifact(&project, "chapters", 1, "md").unwrap(),
            b"changed after completion",
        )
        .unwrap();
        assert!(
            execute(
                &json!({"action":"complete","novel_id":"novel"}),
                p,
                &json!({})
            )
            .is_err()
        );
    }

    #[test]
    fn failed_export_preserves_and_recovers_the_complete_commit() {
        let root = tempfile::tempdir().unwrap();
        let p = root.path();
        let (project, mut state) = configured(p);
        prepare(
            p,
            &project,
            &mut state,
            &json!({"title":"Start","data":{"outline":"Concrete original action"}}),
            &json!({}),
        )
        .unwrap();
        let content = (0..100)
            .map(|n| format!("{n} 她把票据放在桌上，等待车站恢复自己的灯光。\n"))
            .collect::<String>();
        fs::create_dir(p.join("novel")).unwrap();
        fs::write(p.join("novel/novel"), b"fixture obstruction").unwrap();
        assert!(
            execute(
                &json!({"action":"commit_chapter","novel_id":"novel","data":{"content":content}}),
                p,
                &json!({})
            )
            .is_err()
        );
        assert_eq!(
            read_json(&state_path(&project).unwrap()).unwrap()["completed_chapters"],
            0
        );
        assert!(commit_pending(&project).unwrap());
        let journal =
            read_json(&safe_path(&project, "tracking/native-commit.json").unwrap()).unwrap();
        assert!(
            journal["chapter_text"]
                .as_str()
                .unwrap()
                .contains(content.trim())
        );
        fs::remove_file(p.join("novel/novel")).unwrap();
        execute(&json!({"action":"configure","novel_id":"novel","data":{"style_guide":"Preserve established facts."}}),p,&json!({})).unwrap();
        let (_, state) = load_project(p, &json!({"novel_id":"novel"})).unwrap();
        assert_eq!(state["completed_chapters"], 1);
        assert!(!commit_pending(&project).unwrap());
        assert_eq!(
            audit(p, &project, &state).unwrap()["completion_ready"],
            true
        );
    }
}
