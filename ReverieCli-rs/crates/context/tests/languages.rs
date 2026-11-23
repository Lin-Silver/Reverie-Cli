use reverie_context::ContextEngine;
use serde_json::json;
use std::{fs, path::Path};

#[test]
fn script_and_web_resource_grammars_preserve_names_and_real_source() {
    let parent = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/context-tests");
    fs::create_dir_all(&parent).unwrap();
    let dir = tempfile::tempdir_in(parent).unwrap();
    let root = dir.path().join("project");
    fs::create_dir_all(&root).unwrap();
    let fixtures = [
        (
            "logic.zig",
            "pub const limit: u32 = 3;\n/// Saves progress.\npub fn Save() u32 { return limit; }\n",
            "logic.Save",
            "zig",
            "FUNCTION",
        ),
        (
            "page.html",
            "<main id=\"root\"><button id=\"save-game\">Save</button><img id=\"portrait\" src=\"a.png\" /></main>\n",
            "page.save-game",
            "html",
            "PROPERTY",
        ),
        (
            "style.css",
            ".game, #save:hover { color: red; }\n",
            "style.#save:hover",
            "css",
            "PROPERTY",
        ),
        (
            "logic.lua",
            "local Ship = {}\nfunction Ship:save() return 1 end\nfunction run() return Ship:save() end\n",
            "logic.Ship.save",
            "lua",
            "METHOD",
        ),
        (
            "ship.gd",
            "class_name Ship\nextends Node\nconst LIMIT = 3\nvar fuel = 2\nsignal saved\nfunc save():\n    return LIMIT\n",
            "ship.Ship.save",
            "gdscript",
            "METHOD",
        ),
    ];
    for (path, content, ..) in &fixtures {
        fs::write(root.join(path), content).unwrap();
    }
    let mut engine = ContextEngine::open(&root, &dir.path().join("context.sqlite3")).unwrap();
    engine.index(false).unwrap();
    for (_, _, symbol, language, kind) in &fixtures {
        let found = engine
            .lookup(&json!({"query_type":"symbol","query":symbol}))
            .unwrap();
        assert_eq!(found["symbol"]["language"], *language, "{symbol}");
        assert_eq!(found["symbol"]["kind"], *kind, "{symbol}");
        assert!(
            !found["evidence"][0]["content"].as_str().unwrap().is_empty(),
            "{symbol}"
        );
    }
    assert_eq!(
        engine
            .lookup(&json!({"query_type":"symbol","query":"logic.limit"}))
            .unwrap()["symbol"]["kind"],
        "CONSTANT"
    );
    assert!(
        engine
            .lookup(&json!({"query_type":"symbol","query":"logic.Save"}))
            .unwrap()["symbol"]["documentation"]
            .as_str()
            .unwrap()
            .contains("Saves progress")
    );
    assert_eq!(
        engine
            .lookup(&json!({"query_type":"symbol","query":"ship.Ship.fuel"}))
            .unwrap()["parent"]["qualified_name"],
        "ship.Ship"
    );
    assert_eq!(
        engine
            .lookup(&json!({"query_type":"symbol","query":"ship.Ship.saved"}))
            .unwrap()["symbol"]["kind"],
        "PROPERTY"
    );
    let calls = engine
        .lookup(&json!({"query_type":"dependencies","query":"logic.run"}))
        .unwrap();
    assert!(
        calls["references"]
            .as_array()
            .unwrap()
            .iter()
            .any(|reference| reference["to_symbol"] == "logic.Ship.save")
    );
}

#[test]
fn native_grammars_return_real_definitions_bodies_and_scoped_references() {
    let parent = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/context-tests");
    fs::create_dir_all(&parent).unwrap();
    let dir = tempfile::tempdir_in(parent).unwrap();
    let root = dir.path().join("project");
    fs::create_dir_all(&root).unwrap();
    let fixtures = [
        (
            "c.c",
            "struct Ship { int fuel; };\nint helper() { return 1; }\nint save_game() { return helper(); }\n",
            "c.save_game",
            "c",
            "FUNCTION",
        ),
        (
            "cpp.cpp",
            "namespace game { class Ship { public: int tick() { return 1; } }; int save_game() { return 2; } }\n",
            "cpp.game.Ship.tick",
            "cpp",
            "METHOD",
        ),
        (
            "sharp.cs",
            "namespace Game { class Ship { public int Tick() { return 1; } public int Save() { return Tick(); } } }\n",
            "sharp.Game.Ship.Save",
            "csharp",
            "METHOD",
        ),
        (
            "logic.go",
            "package game\n// Saves progress.\nfunc Save() int { return helper() }\nfunc helper() int { return 1 }\ntype Ship struct { Fuel int }\n",
            "logic.Save",
            "go",
            "FUNCTION",
        ),
        (
            "Ship.java",
            "class Ship { int helper() { return 1; } int save() { return helper(); } }\n",
            "Ship.Ship.save",
            "java",
            "METHOD",
        ),
    ];
    for (path, content, ..) in &fixtures {
        fs::write(root.join(path), content).unwrap();
    }
    let mut engine = ContextEngine::open(&root, &dir.path().join("context.sqlite3")).unwrap();
    assert_eq!(engine.index(false).unwrap()["indexed"], fixtures.len());
    for (_, _, symbol, language, kind) in &fixtures {
        let found = engine
            .lookup(&json!({"query_type":"symbol","query":symbol}))
            .unwrap();
        assert_eq!(found["symbol"]["language"], *language, "{symbol}");
        assert_eq!(found["symbol"]["kind"], *kind, "{symbol}");
        assert!(
            found["evidence"][0]["content"]
                .as_str()
                .unwrap()
                .contains("return"),
            "{symbol}"
        );
    }
    let c = engine
        .lookup(&json!({"query_type":"dependencies","query":"c.save_game"}))
        .unwrap();
    assert!(
        c["references"]
            .as_array()
            .unwrap()
            .iter()
            .any(|reference| reference["from_symbol"] == "c.save_game"
                && reference["to_symbol"] == "c.helper"
                && reference["resolution"] == "lexical")
    );
    let java = engine
        .lookup(&json!({"query_type":"dependencies","query":"Ship.Ship.save"}))
        .unwrap();
    assert!(
        java["references"]
            .as_array()
            .unwrap()
            .iter()
            .any(|reference| reference["to_symbol"] == "Ship.Ship.helper")
    );
    let go = engine
        .lookup(&json!({"query_type":"symbol","query":"logic.Ship"}))
        .unwrap();
    assert_eq!(go["symbol"]["kind"], "STRUCT");
    let docs = engine
        .lookup(&json!({"query_type":"symbol","query":"logic.Save"}))
        .unwrap();
    assert!(
        docs["symbol"]["documentation"]
            .as_str()
            .unwrap()
            .contains("Saves progress")
    );
}
