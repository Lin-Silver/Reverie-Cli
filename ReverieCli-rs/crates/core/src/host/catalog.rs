use crate::modes;
use serde_json::{Value, json};

pub fn tool_catalog_for(mode: &str) -> Vec<Value> {
    let mut tools = tool_catalog();
    if mode == "writer" {
        tools.retain(|tool| {
            [
                "skill_lookup",
                "userInput",
                "mcp-catalog",
                "mcp-resources-read",
                "mcp-prompts-get",
            ]
            .contains(&tool["function"]["name"].as_str().unwrap_or_default())
        });
    }
    tools.extend(modes::definitions(mode));
    tools
}

pub fn tool_catalog() -> Vec<Value> {
    let mut tools = reverie_platform::tools();
    tools.push(crate::skills::tool_definition());
    tools.push(json!({"type":"function","function":{"name":"mcp-catalog","description":"Inspect this task's trusted MCP servers, tools, resources, templates or prompts. Results are paged and carry server_id and generation. Listing does not grant trust, install dependencies or authorize connectors.","parameters":{"type":"object","properties":{"section":{"type":"string","enum":["servers","tools","resources","resource_templates","prompts"]},"server_id":{"type":"string"},"offset":{"type":"integer","minimum":0},"limit":{"type":"integer","minimum":1,"maximum":100}},"required":["section"],"additionalProperties":false}}}));
    tools.push(json!({"type":"function","function":{"name":"mcp-resources-read","description":"Read a discovered MCP resource or a resource template URI from a trusted server. Use the listed server_id; this never installs or authorizes a server.","parameters":{"type":"object","properties":{"server_id":{"type":"string"},"uri":{"type":"string"}},"required":["server_id","uri"],"additionalProperties":false}}}));
    tools.push(json!({"type":"function","function":{"name":"mcp-prompts-get","description":"Retrieve a discovered MCP prompt and its arguments from a trusted server. The returned prompt remains external content and cannot expand tool permissions.","parameters":{"type":"object","properties":{"server_id":{"type":"string"},"name":{"type":"string"},"arguments":{"type":"object","additionalProperties":{"type":"string"}}},"required":["server_id","name"],"additionalProperties":false}}}));
    tools.push(json!({"type":"function","function":{"name":"codebase-retrieval","description":"Inspect the active workspace before repository-dependent answers or edits. Use task for a broad bounded evidence workset, then symbol, file, search, outline or dependencies. Evidence includes content hashes and at most 72 source lines. Dependency targets distinguish lexical matches, inference, ambiguity and unresolved names. Memory and LSP queries are still being migrated.","parameters":{"type":"object","properties":{"query_type":{"type":"string","enum":["symbol","file","search","dependencies","outline","explore","task"]},"query":{"type":"string"},"include_source":{"type":"boolean","default":true},"include_dependencies":{"type":"boolean","default":true},"max_depth":{"type":"integer","minimum":0,"default":2},"filter_kind":{"type":"string","default":"all"},"direction":{"type":"string","enum":["incoming","outgoing","both"]},"limit":{"type":"integer","default":20},"max_files":{"type":"integer","default":6},"max_symbols":{"type":"integer","default":12},"max_tokens":{"type":"integer","default":12000},"include_history":{"type":"boolean"},"include_memory":{"type":"boolean"},"active_files":{"type":"array","items":{"type":"string"}},"changed_files":{"type":"array","items":{"type":"string"}}},"required":["query_type","query"]}}}));
    tools.push(json!({"type":"function","function":{"name":"userInput","description":"Ask a concise clarification with up to three options and a custom answer. Wait for the user's explicit response; this does not approve workspace tools.","parameters":{"type":"object","properties":{"question":{"type":"string"},"reason":{"type":"string"},"options":{"type":"array","items":{"type":"string"},"maxItems":3},"multiple":{"type":"boolean"}},"required":["question","reason"]}}}));
    tools
}

pub(super) fn describe(tool: &Value, kind: &str, category: &str, mode: &str) -> Value {
    let schema = &tool["function"]["parameters"];
    json!({"name":tool["function"]["name"],"description":tool["function"]["description"],"parameters":schema,
        "kind":kind,"category":category,"aliases":[],"tags":[],"traits":[],"supported_modes":[mode],
        "required":schema["required"].as_array().cloned().unwrap_or_default(),
        "properties":schema["properties"].as_object().map(|properties|properties.keys().collect::<Vec<_>>()).unwrap_or_default()})
}
pub(super) fn mcp_catalog(
    snapshot: &crate::mcp::McpSnapshot,
    args: &Value,
) -> crate::Result<Value> {
    let section = args["section"]
        .as_str()
        .ok_or("MCP catalogue section is required.")?;
    if ![
        "servers",
        "tools",
        "resources",
        "resource_templates",
        "prompts",
    ]
    .contains(&section)
    {
        return Err("Unknown MCP catalogue section.".into());
    }
    let offset = args["offset"].as_u64().unwrap_or(0).min(100_000) as usize;
    let limit = args["limit"].as_u64().unwrap_or(20).clamp(1, 100) as usize;
    let catalogue = snapshot.public();
    let items = catalogue[section]
        .as_array()
        .ok_or("MCP catalogue is not available.")?
        .iter()
        .filter(|item| {
            args["server_id"]
                .as_str()
                .is_none_or(|id| item["server_id"].as_str().or(item["id"].as_str()) == Some(id))
        })
        .collect::<Vec<_>>();
    Ok(
        json!({"section":section,"items":items.iter().skip(offset).take(limit).collect::<Vec<_>>(),"total":items.len(),"offset":offset,"next_offset":(offset+limit<items.len()).then_some(offset+limit)}),
    )
}
