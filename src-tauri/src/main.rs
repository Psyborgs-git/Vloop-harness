// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.iter().any(|a| a == "--ui") {
        // Launch failsafe egui UI
        let options = eframe::NativeOptions {
            viewport: egui::ViewportBuilder::default()
                .with_inner_size([800.0, 600.0])
                .with_title("Vloop Kernel Failsafe UI"),
            ..Default::default()
        };
        eframe::run_native(
            "Vloop Kernel Failsafe UI",
            options,
            Box::new(|_cc| Ok(Box::<FailsafeUi>::default())),
        ).unwrap();
    } else {
        vloop_harness_lib::run();
    }
}

#[derive(PartialEq)]
enum Tab {
    Processes,
    Vault,
    Logs,
    NetworkFencing,
}

impl Default for Tab {
    fn default() -> Self {
        Self::Processes
    }
}

struct FailsafeUi {
    current_tab: Tab,
    vault_key_input: String,
    vault_val_input: String,
    logs: std::collections::VecDeque<String>,
}

impl Default for FailsafeUi {
    fn default() -> Self {
        let mut logs = std::collections::VecDeque::new();
        logs.push_back("Failsafe UI Started. Kernel is active.".to_string());
        Self {
            current_tab: Tab::default(),
            vault_key_input: String::new(),
            vault_val_input: String::new(),
            logs,
        }
    }
}

impl FailsafeUi {
    fn add_log(&mut self, msg: String) {
        self.logs.push_back(format!("[{}] {}", chrono::Local::now().format("%H:%M:%S"), msg));
        if self.logs.len() > 100 {
            self.logs.pop_front();
        }
    }
}

impl eframe::App for FailsafeUi {
    #[allow(deprecated)]
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::TopBottomPanel::top("top_panel").show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.selectable_value(&mut self.current_tab, Tab::Processes, "Processes");
                ui.selectable_value(&mut self.current_tab, Tab::Vault, "Secure Vault");
                ui.selectable_value(&mut self.current_tab, Tab::Logs, "Logs & Status");
                ui.selectable_value(&mut self.current_tab, Tab::NetworkFencing, "Network Fencing");
            });
        });

        egui::CentralPanel::default().show(ctx, |ui| {
            match self.current_tab {
                Tab::Processes => {
                    ui.heading("Process Management (Native Hypervisor)");
                    ui.label("Manage isolated execution sandboxes and PTY sessions.");
                    ui.add_space(10.0);

                    if ui.button("🚨 Emergency Kill All Sandboxes").clicked() {
                        vloop_harness_lib::modules::terminal::kill_all_sessions();
                        self.add_log("Emergency: Killed all active sandboxes.".to_string());
                    }

                    ui.add_space(10.0);
                    ui.separator();
                    ui.heading("Active Sessions");

                    let sessions = vloop_harness_lib::modules::terminal::list_sessions();
                    if sessions.is_empty() {
                        ui.label("No active sessions.");
                    } else {
                        egui::ScrollArea::vertical().show(ui, |ui| {
                            for session_id in sessions {
                                ui.horizontal(|ui| {
                                    ui.label(&session_id);
                                    if ui.button("Kill").clicked() {
                                        let _ = vloop_harness_lib::modules::terminal::close_session(&session_id);
                                        self.add_log(format!("Killed session: {}", session_id));
                                    }
                                });
                            }
                        });
                    }
                }
                Tab::Vault => {
                    ui.heading("Secure Vault");
                    ui.label("Manage secrets. These are automatically injected as environment variables into new processes.");
                    ui.add_space(10.0);

                    ui.horizontal(|ui| {
                        ui.label("Key:");
                        ui.text_edit_singleline(&mut self.vault_key_input);
                        ui.label("Value:");
                        ui.text_edit_singleline(&mut self.vault_val_input);
                        if ui.button("Save to Vault").clicked() {
                            if !self.vault_key_input.is_empty() {
                                vloop_harness_lib::modules::vault::set_key(&self.vault_key_input, &self.vault_val_input);
                                self.add_log(format!("Updated vault key: {}", self.vault_key_input));
                                self.vault_key_input.clear();
                                self.vault_val_input.clear();
                            }
                        }
                    });

                    ui.add_space(10.0);
                    ui.separator();
                    ui.heading("Current Secrets");

                    let vault_keys = vloop_harness_lib::modules::vault::get_all_keys();
                    if vault_keys.is_empty() {
                        ui.label("Vault is empty.");
                    } else {
                        egui::ScrollArea::vertical().show(ui, |ui| {
                            for (key, _) in vault_keys {
                                ui.horizontal(|ui| {
                                    ui.label(key);
                                    ui.label("********"); // Redact value
                                });
                            }
                        });
                    }
                }
                Tab::Logs => {
                    ui.heading("Transport Logs & Kernel Status");
                    ui.label("Recent hypervisor events.");
                    ui.add_space(10.0);
                    ui.separator();
                    egui::ScrollArea::vertical().stick_to_bottom(true).show(ui, |ui| {
                        for log in &self.logs {
                            ui.label(log);
                        }
                    });
                }
                Tab::NetworkFencing => {
                    ui.heading("Network Fencing");
                    ui.label("Kernel-level proxy rules and domain whitelists.");
                    ui.add_space(10.0);
                    ui.label("(Coming soon: Direct edit of Docker proxy proxy/iptables rules via SQLite config)");
                }
            }
        });
    }

    fn ui(&mut self, _ui: &mut egui::Ui, _frame: &mut eframe::Frame) {}
}
