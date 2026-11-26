use super::*;

pub(super) fn validate_control(card: &Value) -> Result<()> {
    let requirements = as_list(&card["continuity_requirements"]);
    let mut forbidden = vec![];
    let pattern = Regex::new(
        r"(?:不得出现|不要出现|禁止出现|避免出现|不得使用|不要使用|禁止使用)\s*([^。；;\n]+)",
    )?;
    for requirement in requirements {
        for capture in pattern.captures_iter(&display(&requirement)) {
            for term in capture[1].split(['、', ',', '，', '/']) {
                let term = term
                    .trim()
                    .trim_matches(['"', '\'', '“', '”', '‘', '’', '`', '《', '》']);
                if !term.is_empty() {
                    forbidden.push(term.to_owned());
                }
            }
        }
    }
    let body = format!(
        "{} {} {} {}",
        text(card, "outline"),
        text(card, "opening_hook"),
        text(card, "ending_hook"),
        serde_json::to_string(&card["scene_beats"])?
    );
    let found = forbidden
        .into_iter()
        .filter(|term| body.contains(term))
        .collect::<Vec<_>>();
    if found.is_empty() {
        Ok(())
    } else {
        Err(format!(
            "Control card violates its continuity requirements: {}",
            found.join(", ")
        )
        .into())
    }
}

pub(super) fn report(
    content: &str,
    target: u64,
    minimum: u64,
    chapter_minimum: u64,
    prior: &str,
) -> Result<Value> {
    let chars = length(content);
    let han = content
        .chars()
        .filter(|ch| matches!(ch,'\u{3400}'..='\u{4dbf}'|'\u{4e00}'..='\u{9fff}'))
        .count();
    let paragraphs = content
        .lines()
        .map(str::trim)
        .filter(|line| line.chars().count() >= 20)
        .collect::<Vec<_>>();
    let unique = paragraphs.iter().copied().collect::<HashSet<_>>();
    let duplicates = paragraphs.len() - unique.len();
    let ratio = duplicates as f64 / paragraphs.len().max(1) as f64;
    let marker = Regex::new(
        r"(?im)\b(?:TODO|TBD|PLACEHOLDER)\b|\[(?:to be written|pending)\]|[\[【（(][^\[\]【】（）()\n]*(?:待补|省略)[^\[\]【】（）()\n]*[\]】）)]|^[ \t]*(?:待补|省略)[ \t\r。.!！…]*$|(?:此处|下文|后文|正文)(?:内容|场景|情节|描写)?(?:待补|省略)",
    )?;
    let placeholders = marker
        .find_iter(content)
        .map(|item| item.as_str().to_owned())
        .collect::<std::collections::BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let mut tics = serde_json::Map::new();
    let mut overused = serde_json::Map::new();
    let tic_limit = 2usize.max(chars.div_ceil(1000) * 2);
    for term in [
        "微微",
        "缓缓",
        "仿佛",
        "似乎",
        "不由自主",
        "一丝",
        "像是被什么",
        "说不出话",
        "空气中弥漫",
    ] {
        let count = content.matches(term).count();
        if count > 0 {
            tics.insert(term.into(), json!(count));
            if count > tic_limit {
                overused.insert(term.into(), json!(count));
            }
        }
    }
    let density =
        tics.values().filter_map(Value::as_u64).sum::<u64>() as f64 / chars.max(1) as f64 * 1000.0;
    let compact = content
        .chars()
        .filter(|ch| !ch.is_whitespace() && !matches!(ch, '\u{1c}'..='\u{1f}'))
        .collect::<Vec<_>>();
    let prior = prior
        .chars()
        .filter(|ch| !ch.is_whitespace() && !matches!(ch, '\u{1c}'..='\u{1f}'))
        .collect::<Vec<_>>();
    let passages = prior.windows(64).collect::<HashSet<_>>();
    let duplicate = compact
        .windows(64)
        .find(|passage| passages.contains(*passage))
        .map(|passage| passage.iter().collect::<String>())
        .unwrap_or_default();
    let control_minimum = if chapter_minimum > 0 {
        chapter_minimum
    } else {
        scaled_chars(target, 70)?
    }
    .max(350);
    let required = control_minimum.max(minimum);
    let mut issues = vec![];
    if (chars as u64) < required {
        issues.push(format!(
            "Only {chars} non-whitespace characters; planned-delivery minimum is {required}."
        ));
    }
    if ratio > 0.12 {
        issues.push(format!(
            "Duplicate paragraph ratio is {:.1}%.",
            ratio * 100.0
        ));
    }
    if !placeholders.is_empty() {
        issues.push(format!(
            "Placeholder text remains: {}.",
            placeholders
                .iter()
                .take(5)
                .cloned()
                .collect::<Vec<_>>()
                .join(", ")
        ));
    }
    if !overused.is_empty() {
        issues.push(format!(
            "Generated-prose tics exceed the repetition threshold: {}.",
            serde_json::to_string(&overused)?
        ));
    }
    if density > 10.0 {
        issues.push(format!(
            "Generated-prose tic density is {density:.1} per 1,000 characters."
        ));
    }
    if !duplicate.is_empty() {
        issues.push("A 64-character passage repeats an earlier chapter.".into());
    }
    let mut findings = vec![];
    let mut seen = HashSet::new();
    let locations = |term: &str| {
        content
            .lines()
            .enumerate()
            .filter_map(|(index, line)| line.contains(term).then_some(index + 1))
            .collect::<Vec<_>>()
    };
    for paragraph in &paragraphs {
        if seen.insert(*paragraph)
            && paragraphs.iter().filter(|item| *item == paragraph).count() > 1
        {
            findings.push(json!({"kind":"duplicate_paragraph","severity":if ratio>0.12{"blocking"}else{"review"},"quote":paragraph,"locations":locations(paragraph),"evidence_type":"deterministic_text_match","impact":"相同段落重复出现。","suggestion":"核对有意回声；保留有效叙事作用并补写新的行动或后果。"}));
            if findings.len() >= 8 {
                break;
            }
        }
    }
    for term in placeholders.iter().take(5) {
        findings.push(json!({"kind":"placeholder","severity":"blocking","quote":term,"locations":locations(term),"evidence_type":"deterministic_text_match","impact":"原生门禁识别到待写标记。","suggestion":"完成缺失的正文后重新提交。"}));
    }
    for term in overused.keys() {
        findings.push(json!({"kind":"style_tic","severity":"blocking","quote":term,"locations":locations(term),"evidence_type":"deterministic_text_match","impact":"固定表达超过重复阈值；计数不评判文笔。","suggestion":"核对每处是否增加新的信息或反应。"}));
    }
    if !duplicate.is_empty() {
        findings.push(json!({"kind":"cross_chapter_copy","severity":"blocking","quote":duplicate,"locations":[],"evidence_type":"deterministic_non_whitespace_match","impact":"前章有相同的64个非空白字符。","suggestion":"核对是否误复制；从尚未发生的事件继续。"}));
    }
    Ok(
        json!({"chars":chars,"han_chars":han,"target_chars":target,"minimum_chars":required,"control_card_minimum_chars":control_minimum,
        "delivery_minimum_chars":minimum,"duplicate_paragraphs":duplicates,"duplicate_ratio":(ratio*10000.0).round()/10000.0,"placeholders":placeholders,
        "style_tic_counts":tics,"style_tic_density_per_1000":(density*100.0).round()/100.0,"overused_style_tics":overused,"cross_chapter_duplicate_passage":duplicate,
        "blocking_issues":issues,"passed":issues.is_empty(),"assessment":"deterministic_checks_only",
        "limitations":"Text matches and length gates do not rate prose, character depth, emotional credibility or commercial appeal.","findings":findings}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn quality_keeps_the_python_mechanical_gate_contract() {
        let repeated =
            "This paragraph repeats without any new information or changed outcome.\n".repeat(30);
        assert!(
            report(&repeated, 500, 350, 0, "").unwrap()["blocking_issues"]
                .as_array()
                .unwrap()
                .iter()
                .any(|issue| issue.as_str().unwrap().contains("Duplicate"))
        );
        assert!(
            !report("正文[待补关键场景]", 500, 350, 0, "").unwrap()["placeholders"]
                .as_array()
                .unwrap()
                .is_empty()
        );
        assert!(
            !report(&"仿佛".repeat(10), 500, 350, 0, "").unwrap()["overused_style_tics"]
                .as_object()
                .unwrap()
                .is_empty()
        );
        let prior="A deliberately identical sixty-four-character passage that must fail cross-chapter reuse. ".repeat(10);
        assert!(
            !report(&prior, 500, 350, 0, &prior).unwrap()["cross_chapter_duplicate_passage"]
                .as_str()
                .unwrap()
                .is_empty()
        );
    }
}
