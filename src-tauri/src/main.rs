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

#[derive(Default)]
struct FailsafeUi {
    // Add any state needed here
}

impl eframe::App for FailsafeUi {
    #[allow(deprecated)]
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading("Vloop Kernel Failsafe UI");
            ui.label("This is the native Rust GUI for managing the kernel independently of the web frontend.");
            if ui.button("Emergency Kill All Sandboxes").clicked() {
                // TODO: Call into sandbox manager to kill all docker/pty sessions
            }
        });
    }

    fn ui(&mut self, _ui: &mut egui::Ui, _frame: &mut eframe::Frame) {}
}
