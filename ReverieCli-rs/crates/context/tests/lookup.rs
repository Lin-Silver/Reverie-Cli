use reverie_context::ContextEngine;
use serde_json::{Value, json};
use std::{fs, path::Path};

fn directory() -> tempfile::TempDir {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/context-tests");
    fs::create_dir_all(&root).unwrap();
    tempfile::tempdir_in(root).unwrap()
}

#[test]
fn metadata_and_dependencies_follow_nested_scopes_and_changed_targets() {
    let dir = directory();
    let project = dir.path().join("project");
    fs::create_dir_all(&project).unwrap();
    fs::write(project.join("ship.py"), "class Ship:\n    def save(self):\n        def helper():\n            return 1\n        helper()\n        self.tick()\n    def tick(self):\n        return 2\ndef caller():\n    duplicate()\n    absent()\n").unwrap();
    fs::write(project.join("a.py"), "def duplicate():\n    return 1\n").unwrap();
    fs::write(project.join("b.py"), "def duplicate():\n    return 2\n").unwrap();
    fs::write(
        project.join("logic.rs"),
        "trait Step {}\nstruct Ship;\nimpl Step for Ship {}\nmod nested { pub fn tick() {} }\n",
    )
    .unwrap();
    let mut engine = ContextEngine::open(&project, &dir.path().join("context.sqlite3")).unwrap();
    engine.index(false).unwrap();
    let query = |kind, text| json!({"query_type":kind,"query":text});
    let method = engine.lookup(&query("symbol", "Ship.save")).unwrap();
    assert_eq!(method["symbol"]["kind"], "METHOD");
    assert_eq!(method["symbol"]["language"], "python");
    assert_eq!(method["symbol"]["signature"], "def save(self):");
    assert_eq!(method["parent"]["qualified_name"], "ship.Ship");
    assert_eq!(
        method["children"][0]["qualified_name"],
        "ship.Ship.save.helper"
    );
    assert_eq!(method["children"][0]["kind"], "FUNCTION");
    assert!(
        method["references"]
            .as_array()
            .unwrap()
            .iter()
            .any(|edge| edge["target_text"] == "self.tick"
                && edge["to_symbol"] == "ship.Ship.tick"
                && edge["resolution"] == "inferred_receiver_scope")
    );
    let helper = engine
        .lookup(&query("symbol", "ship.Ship.save.helper"))
        .unwrap();
    assert!(
        helper["references"]
            .as_array()
            .unwrap()
            .iter()
            .any(|edge| edge["dep_type"] == "CALLS" && edge["resolution"] == "lexical")
    );
    let caller = engine
        .lookup(&query("dependencies", "ship.caller"))
        .unwrap();
    assert!(
        caller["references"]
            .as_array()
            .unwrap()
            .iter()
            .any(|edge| edge["target_text"] == "duplicate"
                && edge["resolution"] == "ambiguous"
                && edge["to_symbol"].is_null())
    );
    assert!(
        caller["references"]
            .as_array()
            .unwrap()
            .iter()
            .any(|edge| edge["target_text"] == "absent" && edge["resolution"] == "unresolved")
    );
    let rust = engine.lookup(&query("dependencies", "logic.Ship")).unwrap();
    let module = engine.lookup(&query("symbol", "logic.nested")).unwrap();
    assert_eq!(module["symbol"]["kind"], "MODULE");
    assert_eq!(module["children"][0]["qualified_name"], "logic.nested.tick");
    assert!(
        rust["references"]
            .as_array()
            .unwrap()
            .iter()
            .any(|edge| edge["from_symbol"] == "logic.Ship"
                && edge["to_symbol"] == "logic.Step"
                && edge["dep_type"] == "IMPLEMENTS")
    );
    let outline = engine.lookup(&query("outline", "./ship.py")).unwrap();
    assert!(outline["evidence"].as_array().unwrap().is_empty());
    assert!(engine.lookup(&query("file", "../ship.py")).is_err());
    fs::remove_file(project.join("b.py")).unwrap();
    engine.index(false).unwrap();
    let caller = engine
        .lookup(&query("dependencies", "ship.caller"))
        .unwrap();
    assert!(
        caller["references"]
            .as_array()
            .unwrap()
            .iter()
            .any(|edge| edge["to_symbol"] == "a.duplicate"
                && edge["resolution"] == "inferred_unique_name")
    );
    fs::write(project.join("a.py"), "def changed_target(): pass\n").unwrap();
    assert!(
        engine
            .lookup(&query("dependencies", "ship.caller"))
            .is_err()
    );
    engine.index(false).unwrap();
    let caller = engine
        .lookup(&query("dependencies", "ship.caller"))
        .unwrap();
    assert!(
        caller["references"]
            .as_array()
            .unwrap()
            .iter()
            .any(|edge| edge["target_text"] == "duplicate" && edge["resolution"] == "unresolved")
    );
    fs::write(project.join("ship.py"), "class Replaced: pass\n").unwrap();
    assert!(engine.lookup(&query("symbol", "ship.Ship.save")).is_err());
    engine.index(false).unwrap();
    assert!(engine.lookup(&query("symbol", "ship.Ship.save")).is_err());
}

#[test]
fn exact_symbol_and_custom_budget_are_preserved_with_bounded_evidence() {
    let dir = directory();
    let project = dir.path().join("project");
    fs::create_dir_all(&project).unwrap();
    let mut code = (0..230)
        .map(|index| format!("def save_game_{index}():\n    pass\n"))
        .collect::<String>();
    code.push_str("def save_game():\n    pass\n");
    fs::write(project.join("a.py"), code).unwrap();
    fs::write(project.join("z.py"), "def save_game():\n    pass\n").unwrap();
    fs::write(
        project.join("story.txt"),
        (0..150)
            .map(|line| format!("marker {line} {}\n", "飞船😀".repeat(240)))
            .collect::<String>(),
    )
    .unwrap();
    let mut engine = ContextEngine::open(&project, &dir.path().join("context.sqlite3")).unwrap();
    engine.index(false).unwrap();
    assert!(
        engine
            .lookup(&json!({"query_type":"symbol","query":"save_game"}))
            .is_err()
    );
    let exact = engine
        .lookup(&json!({"query_type":"symbol","query":"z.save_game"}))
        .unwrap();
    assert_eq!(exact["symbol"]["file_path"], "z.py");
    let task = engine
        .lookup(&json!({"query_type":"task","query":"marker","max_tokens":30000}))
        .unwrap();
    assert_eq!(task["max_tokens"], 30000);
    assert!(task["estimated_tokens"].as_u64().unwrap() > 12000);
    for hit in task["evidence"].as_array().unwrap() {
        assert!(hit["end_line"].as_u64().unwrap() - hit["start_line"].as_u64().unwrap() < 72);
        assert!(hit["revision"].as_i64().unwrap() > 0);
        assert_eq!(hit["content_hash"].as_str().unwrap().len(), 64);
    }
    let empty: Value = engine
        .lookup(&json!({"query_type":"task","query":"marker","max_tokens":0}))
        .unwrap();
    assert!(empty["evidence"].as_array().unwrap().is_empty());
}
