use anyhow::{anyhow, Result};
use std::path::{Path, PathBuf};

/// Resolve `user_path` relative to `root` and ensure it does not escape.
pub fn resolve_safe(root: &Path, user_path: &str) -> Result<PathBuf> {
    let joined = root.join(user_path);
    let canonical = joined
        .canonicalize()
        .or_else(|_| {
            // Path may not exist yet — canonicalize parent
            let parent = joined.parent().unwrap_or(root);
            parent
                .canonicalize()
                .map(|p| p.join(joined.file_name().unwrap_or_default()))
        })
        .unwrap_or(joined.clone());

    let root_canonical = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());

    if !canonical.starts_with(&root_canonical) {
        return Err(anyhow!(
            "Path escape detected: '{}' is outside root '{}'",
            canonical.display(),
            root_canonical.display()
        ));
    }
    Ok(canonical)
}
