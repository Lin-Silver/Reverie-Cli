use crate::Result;
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs, path::Path};

pub const MOTION_ENTRY: &str = "runtime/bin/reverie-motion.mjs";
const FILES: &str = include_str!("../../../../resources/builtin_skills/reverie-motion-files.json");
const GUARD: &[u8] = include_bytes!("../../../../resources/builtin_skills/reverie-motion-host.mjs");

pub fn motion_entry(package: &Path) -> std::path::PathBuf {
    dunce::simplified(package).join(MOTION_ENTRY)
}

// Only the direct Node script operand can receive this exception. The installation
// root comes from the running executable, never from project metadata or the model.
pub(super) fn motion_guard(install: &Path, operand: &Path) -> Result<Option<(String, String)>> {
    if !operand.is_absolute() || !operand.ends_with(Path::new("reverie-motion").join(MOTION_ENTRY))
    {
        return Ok(None);
    }
    let assets = install.canonicalize()?.join("builtin_skills");
    let package = assets.join("reverie-motion");
    if operand
        .components()
        .any(|c| matches!(c, std::path::Component::ParentDir))
        || operand.canonicalize().ok().as_deref() != Some(package.join(MOTION_ENTRY).as_path())
    {
        return Ok(None);
    }
    let manifest = assets.join("reverie-builtin-skills.json");
    if manifest.canonicalize()? != manifest || !manifest.is_file() {
        return Err("Invalid builtin skill manifest location.".into());
    }
    let registered: Vec<String> = serde_json::from_slice(&fs::read(&manifest)?)?;
    if !registered.iter().any(|p| p == "reverie-motion/SKILL.md") {
        return Err("Motion is not registered in the installed builtin skill manifest.".into());
    }
    for (relative, hash) in serde_json::from_str::<BTreeMap<String, String>>(FILES)? {
        let file = package.join(relative);
        if file.canonicalize()? != file || !file.is_file() {
            return Err("Invalid installed Motion file location.".into());
        }
        let digest: String = Sha256::digest(fs::read(&file)?)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect();
        if digest != hash {
            return Err("Installed Motion files differ from the reviewed package.".into());
        }
    }
    let guard = assets.join("reverie-motion-host.mjs");
    if guard.canonicalize()? != guard || fs::read(&guard)? != GUARD {
        return Err("Installed Motion command guard differs from the native build.".into());
    }
    Ok(Some((
        url::Url::from_file_path(guard)
            .map_err(|_| "Invalid Motion guard file URL.")?
            .into(),
        motion_entry(&package)
            .into_os_string()
            .into_string()
            .map_err(|_| "Invalid Motion entry path.")?,
    )))
}

pub(super) fn node(root: &Path) -> Result<String> {
    let filename = if cfg!(windows) { "node.exe" } else { "node" };
    let workspace = root.canonicalize()?;
    std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default())
        .filter(|directory| directory.is_absolute())
        .filter_map(|dir| dir.join(filename).canonicalize().ok())
        .find(|path| path.is_file() && !path.starts_with(&workspace))
        .and_then(|path| path.into_os_string().into_string().ok())
        .ok_or_else(|| {
            "Install Node on PATH outside the workspace to run the builtin Motion skill.".into()
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_the_registered_unchanged_motion_package_has_an_external_entry() {
        let tmp = tempfile::tempdir().unwrap();
        let assets = tmp.path().join("builtin_skills");
        let package = assets.join("reverie-motion");
        let source = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../resources/builtin_skills/reverie-motion");
        for relative in serde_json::from_str::<BTreeMap<String, String>>(FILES)
            .unwrap()
            .keys()
        {
            let file = package.join(relative);
            fs::create_dir_all(file.parent().unwrap()).unwrap();
            fs::copy(source.join(relative), file).unwrap();
        }
        fs::write(assets.join("reverie-motion-host.mjs"), GUARD).unwrap();
        let manifest = assets.join("reverie-builtin-skills.json");
        let entry = package.join(MOTION_ENTRY);
        fs::write(&manifest, "[]").unwrap();
        assert!(motion_guard(tmp.path(), &entry).is_err());
        fs::write(manifest, r#"["reverie-motion/SKILL.md"]"#).unwrap();
        assert!(motion_guard(tmp.path(), &entry).unwrap().is_some());
        assert!(
            motion_guard(tmp.path(), &package.join("runtime/lib/cli.mjs"))
                .unwrap()
                .is_none()
        );
        fs::write(package.join("runtime/lib/cli.mjs"), "// changed module").unwrap();
        assert!(motion_guard(tmp.path(), &entry).is_err());
    }
}
