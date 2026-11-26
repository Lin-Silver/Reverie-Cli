//! Installed extension content, activation and component registration.
pub mod manifest;
pub mod package;
mod sources;
mod store;
pub use store::{PluginLease, PluginStore};

#[cfg(test)]
mod tests;

pub(crate) fn validate_components(
    root: &std::path::Path,
    metadata: &manifest::Metadata,
) -> crate::Result<()> {
    for component in &metadata.components {
        match component.kind.as_str() {
            "mcp" => {
                crate::mcp::ServerConfig::parse(
                    &component.name,
                    "extension",
                    &component.configuration,
                )?;
            }
            "skill" | "command" | "agent" | "runtime" => {
                package::checked_path(root, &component.path)?;
            }
            "lsp"
                if component.configuration["command"]
                    .as_str()
                    .is_none_or(|value| value.trim().is_empty() || value.contains('\0')) =>
            {
                return Err("Language server requires an executable command.".into());
            }
            _ => {}
        }
    }
    Ok(())
}
