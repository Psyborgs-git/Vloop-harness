use std::process::{Command, Stdio};
use std::thread;
use std::io::{BufRead, BufReader};

pub fn start_python_supervisor() {
    thread::spawn(|| {
        println!("Starting Python Control Plane Supervisor...");
        
        loop {
            let mut child = Command::new("uv")
                .arg("run")
                .arg("main.py")
                .current_dir("../control-plane")
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .expect("Failed to start python control plane");

            if let Some(stdout) = child.stdout.take() {
                let reader = BufReader::new(stdout);
                for line in reader.lines() {
                    match line {
                        Ok(l) => println!("[Python CP STDOUT]: {}", l),
                        Err(e) => eprintln!("Error reading stdout: {}", e),
                    }
                }
            }

            let status = child.wait().expect("Failed to wait on python control plane");
            println!("Python Control Plane exited with status: {}", status);

            println!("Restarting Control Plane in 3 seconds...");
            thread::sleep(std::time::Duration::from_secs(3));
        }
    });
}
