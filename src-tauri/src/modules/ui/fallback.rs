use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindowBuilder};
use std::fs;

pub fn show_fallback_ui(app: &AppHandle, logs: &str, error: &str) -> Result<(), Box<dyn std::error::Error>> {
    let html_content = format!(
        r#"
        <!DOCTYPE html>
        <html>
        <head>
            <title>Vloop Harness - Recovery</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 2rem; background: #1a1a1a; color: #fff; }}
                h1 {{ color: #ff5555; }}
                .error {{ padding: 1rem; background: #2a1111; border-left: 4px solid #ff5555; margin-bottom: 1rem; }}
                pre {{ background: #222; padding: 1rem; overflow-x: auto; font-size: 0.9rem; }}
                button {{ background: #4caf50; color: white; border: none; padding: 0.5rem 1rem; cursor: pointer; font-size: 1rem; border-radius: 4px; }}
                button:hover {{ background: #45a049; }}
            </style>
        </head>
        <body>
            <h1>Boot Error</h1>
            <div class="error">
                <strong>Error:</strong> {}
            </div>
            <h3>Boot Logs:</h3>
            <pre>{}</pre>
            <div>
                <button onclick="window.__TAURI_INTERNALS__.invoke('retry_boot')">Retry Boot</button>
            </div>
        </body>
        </html>
        "#,
        error, logs
    );

    let fallback_path = app.path().app_data_dir()?.join("fallback.html");
    fs::create_dir_all(fallback_path.parent().unwrap())?;
    fs::write(&fallback_path, html_content)?;

    let url = WebviewUrl::App(fallback_path);

    if let Some(main_window) = app.get_webview_window("main") {
        main_window.close()?;
    }

    WebviewWindowBuilder::new(app, "fallback", url)
        .title("Vloop Harness - Recovery")
        .inner_size(800.0, 600.0)
        .build()?;

    Ok(())
}
