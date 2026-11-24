use std::{env, fs, io, path::Path};

fn copy(source: &Path, target: &Path, base: &Path, skills: &mut Vec<String>) -> io::Result<()> {
    if fs::symlink_metadata(source)?.file_type().is_symlink()
        || fs::symlink_metadata(target).is_ok_and(|metadata| metadata.file_type().is_symlink())
    {
        return Err(io::Error::other(
            "Builtin build assets must not traverse links.",
        ));
    }
    if source.is_dir() {
        fs::create_dir_all(target)?;
        let mut entries = fs::read_dir(source)?.collect::<io::Result<Vec<_>>>()?;
        entries.sort_by_key(|entry| entry.file_name());
        for entry in entries {
            if [".git", "__pycache__", "node_modules", ".venv", "venv"]
                .iter()
                .any(|skip| entry.file_name() == std::ffi::OsStr::new(skip))
            {
                continue;
            }
            copy(&entry.path(), &target.join(entry.file_name()), base, skills)?;
        }
    } else {
        fs::copy(source, target)?;
        if source.file_name() == Some(std::ffi::OsStr::new("SKILL.md")) {
            skills.push(
                source
                    .strip_prefix(base)
                    .map_err(io::Error::other)?
                    .to_string_lossy()
                    .replace('\\', "/"),
            );
        }
    }
    Ok(())
}

fn main() -> io::Result<()> {
    let source = std::path::PathBuf::from(
        env::var_os("CARGO_MANIFEST_DIR")
            .ok_or_else(|| io::Error::other("CLI build directory is missing."))?,
    )
    .join("../../resources/builtin_skills");
    let output = std::path::PathBuf::from(
        env::var_os("OUT_DIR")
            .ok_or_else(|| io::Error::other("Cargo output directory is missing."))?,
    );
    let profile = output
        .ancestors()
        .nth(3)
        .ok_or_else(|| io::Error::other("Cargo profile directory is missing."))?;
    let target = profile.join("builtin_skills");
    println!("cargo:rerun-if-changed={}", source.display());
    let mut skills = Vec::new();
    copy(&source, &target, &source, &mut skills)?;
    skills.sort();
    let manifest = target.join("reverie-builtin-skills.json");
    if fs::symlink_metadata(&manifest).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
        return Err(io::Error::other(
            "Builtin build manifest must not be a link.",
        ));
    }
    let temporary = target.join(format!(".manifest-{}.json", std::process::id()));
    let bytes = serde_json::to_vec_pretty(&skills)?;
    fs::write(&temporary, bytes)?;
    fs::rename(temporary, manifest)?;
    Ok(())
}
