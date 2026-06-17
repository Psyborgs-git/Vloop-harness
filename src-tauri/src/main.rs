// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod fs;
mod sys;
mod supervisor;

#[tauri::command]
async fn dispatch_task(task_id: String, objective: String) -> Result<String, String> {
    // In a real implementation, we'd use tonic to send a gRPC request to Python.
    // For scaffolding, we simulate this call.
    println!("Dispatching task {} to Python Control Plane: {}", task_id, objective);
    // Simulate latency
    tokio::time::sleep(std::time::Duration::from_secs(1)).await;
    Ok(format!("Task {} dispatched successfully.", task_id))
}

fn main() {
    println!("VLoop Microkernel Booting...");

    // 1. Probe Memory Limits
    let limits = sys::probe_memory();

    // 2. Initialize VLoop Filesystem boundaries
    let vloop_home = fs::get_vloop_home().expect("Failed to get vloop home");
    let config = fs::ActiveConfig {
        max_memory_bytes: limits.available_for_sandbox,
        data_dir: vloop_home.to_string_lossy().to_string(),
    };

    if let Err(e) = fs::initialize_filesystem(&config) {
        eprintln!("Failed to initialize filesystem: {}", e);
        std::process::exit(1);
    }

    // 3. Start Python Supervisor in background
    supervisor::start_python_supervisor();

    // 4. Boot Tauri Mission Control UI
    tauri::Builder::default()
        .plugin(tauri_plugin_store::Builder::new().build())
        .invoke_handler(tauri::generate_handler![dispatch_task])
        .setup(|_app| {
            println!("Tauri UI initialized.");
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
