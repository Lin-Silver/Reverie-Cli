use std::process::Command;
use tempfile::TempDir;

fn reverie_bin() -> &'static str {
    env!("CARGO_BIN_EXE_reverie")
}

#[test]
fn version_flag_prints_compatible_line() {
    let output = Command::new(reverie_bin())
        .arg("--version")
        .output()
        .expect("run reverie --version");
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.starts_with("Reverie Cli v"));
}

#[test]
fn prompt_mode_writes_report_json() {
    let temp = TempDir::new().unwrap();
    let report = temp.path().join("artifacts/report.json");
    let output = Command::new(reverie_bin())
        .arg(temp.path())
        .arg("--no-index")
        .arg("-p")
        .arg("hello rust")
        .arg("--report-file")
        .arg(&report)
        .output()
        .expect("run prompt mode");
    assert!(output.status.success());
    let report_text = std::fs::read_to_string(report).unwrap();
    let value: serde_json::Value = serde_json::from_str(&report_text).unwrap();
    assert_eq!(value["success"], true);
    assert_eq!(value["mode"], "reverie");
    assert!(value["output_text"]
        .as_str()
        .unwrap_or_default()
        .contains("hello rust"));
}

#[test]
fn index_only_scans_workspace() {
    let temp = TempDir::new().unwrap();
    std::fs::write(temp.path().join("main.rs"), "fn main() {}\n").unwrap();
    let output = Command::new(reverie_bin())
        .arg("--index-only")
        .arg(temp.path())
        .output()
        .expect("run index only");
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Files scanned:"));
    assert!(stdout.contains("Symbols extracted:"));
}
