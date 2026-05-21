use std::process::Command;

#[test]
fn cargo_metadata_can_see_workspace() {
    let output = Command::new("cargo")
        .arg("metadata")
        .arg("--no-deps")
        .output()
        .expect("cargo metadata should run");
    assert!(output.status.success());
}
