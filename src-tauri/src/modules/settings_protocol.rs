use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use tauri::http::{Response, StatusCode, header};

// Returns the static HTML for our custom Settings page
pub fn get_settings_html() -> String {
    include_str!("ui/settings.html").to_string()
}

// Helper to find the .env file path
pub fn get_env_path(repo_root: &Path) -> PathBuf {
    repo_root.join(".env")
}

// Helper to read all variables from the .env file into a HashMap
pub fn read_env_vars(repo_root: &Path) -> HashMap<String, String> {
    let mut vars = HashMap::new();
    let env_path = get_env_path(repo_root);

    // If .env doesn't exist, try reading .env.example as fallback
    let content = if env_path.exists() {
        fs::read_to_string(&env_path).unwrap_or_default()
    } else {
        let example_path = repo_root.join(".env.example");
        if example_path.exists() {
            fs::read_to_string(&example_path).unwrap_or_default()
        } else {
            String::new()
        }
    };

    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        if let Some(pos) = trimmed.find('=') {
            let key = trimmed[..pos].trim().to_string();
            let mut clean_value = trimmed[pos + 1..].trim().to_string();
            // Strip quotes if any
            #[allow(clippy::collapsible_if)]
            if (clean_value.starts_with('"') && clean_value.ends_with('"'))
                || (clean_value.starts_with('\'') && clean_value.ends_with('\''))
            {
                if clean_value.len() >= 2 {
                    clean_value = clean_value[1..clean_value.len() - 1].to_string();
                }
            }
            vars.insert(key, clean_value);
        }
    }

    vars
}

// Helper to write/update specific variables in .env file, preserving comments and format
pub fn update_env_file(repo_root: &Path, updates: &HashMap<String, String>) -> Result<(), String> {
    let env_path = get_env_path(repo_root);
    let mut lines: Vec<String> = Vec::new();

    let content = if env_path.exists() {
        fs::read_to_string(&env_path).map_err(|e| e.to_string())?
    } else {
        let example_path = repo_root.join(".env.example");
        if example_path.exists() {
            fs::read_to_string(&example_path).unwrap_or_default()
        } else {
            String::new()
        }
    };

    let mut keys_found = HashMap::new();
    for key in updates.keys() {
        keys_found.insert(key.clone(), false);
    }

    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            lines.push(line.to_string());
            continue;
        }

        if let Some(pos) = trimmed.find('=') {
            let key = trimmed[..pos].trim();
            if updates.contains_key(key) {
                let value = updates.get(key).unwrap();
                lines.push(format!("{}={}", key, value));
                keys_found.insert(key.to_string(), true);
                continue;
            }
        }
        lines.push(line.to_string());
    }

    // Append keys that weren't found in the existing .env file
    for (key, found) in keys_found {
        if !found {
            if let Some(value) = updates.get(&key) {
                lines.push(format!("{}={}", key, value));
            }
        }
    }

    let new_content = lines.join("\n") + "\n";
    fs::write(&env_path, new_content).map_err(|e| e.to_string())?;

    // Also update current process env vars so dynamic reloads pick them up immediately
    for (key, value) in updates {
        std::env::set_var(key, value);
    }

    Ok(())
}

// Custom URI scheme protocol handler for Tauri v2
pub fn handle_vloop_protocol<R: tauri::Runtime>(
    _ctx: tauri::UriSchemeContext<'_, R>,
    request: tauri::http::Request<Vec<u8>>,
) -> tauri::http::Response<Vec<u8>> {
    let path = request.uri().path();
    let host = request.uri().host();

    // Support both vloop://settings and http://vloop.localhost/settings (Windows fallback)
    let is_settings = host == Some("settings") || path.contains("settings");

    if is_settings {
        let html = get_settings_html();
        Response::builder()
            .status(StatusCode::OK)
            .header(header::CONTENT_TYPE, "text/html; charset=utf-8")
            // Prevent CORS or external resource restriction issues if they occur
            .header(header::ACCESS_CONTROL_ALLOW_ORIGIN, "*")
            .body(html.as_bytes().to_vec())
            .unwrap()
    } else {
        Response::builder()
            .status(StatusCode::NOT_FOUND)
            .header(header::CONTENT_TYPE, "text/plain")
            .body("Not Found".as_bytes().to_vec())
            .unwrap()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_read_and_update_env_vars() {
        let temp_dir = std::env::temp_dir().join(format!("vloop_test_{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&temp_dir).unwrap();

        // Write a mock .env file
        let env_file_path = temp_dir.join(".env");
        std::fs::write(
            &env_file_path,
            "# Test env file\nTEST_KEY=initial_value\n# Another comment\nOTHER_KEY=\"quoted_value\"\n",
        )
        .unwrap();

        // Read variables
        let vars = read_env_vars(&temp_dir);
        assert_eq!(vars.get("TEST_KEY").unwrap(), "initial_value");
        assert_eq!(vars.get("OTHER_KEY").unwrap(), "quoted_value");

        // Update variables
        let mut updates = HashMap::new();
        updates.insert("TEST_KEY".to_string(), "new_value".to_string());
        updates.insert("NEW_KEY".to_string(), "brand_new_value".to_string());

        update_env_file(&temp_dir, &updates).unwrap();

        // Read variables back
        let updated_vars = read_env_vars(&temp_dir);
        assert_eq!(updated_vars.get("TEST_KEY").unwrap(), "new_value");
        assert_eq!(updated_vars.get("OTHER_KEY").unwrap(), "quoted_value"); // should be preserved
        assert_eq!(updated_vars.get("NEW_KEY").unwrap(), "brand_new_value"); // should be added

        // Clean up
        let _ = std::fs::remove_dir_all(temp_dir);
    }
}
