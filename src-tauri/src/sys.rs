use sysinfo::System;

pub struct MemoryLimits {
    pub total_memory: u64,
    pub available_for_sandbox: u64,
}

pub fn probe_memory() -> MemoryLimits {
    let mut sys = System::new_all();
    sys.refresh_all();

    let total_memory = sys.total_memory();
    
    // Safety thresholds (in bytes)
    let os_baseline = 2_u64 * 1024 * 1024 * 1024; // 2GB OS & background apps baseline
    let safety_buffer = 1_u64 * 1024 * 1024 * 1024; // 1GB safety buffer for microkernel/Tauri

    let overhead = os_baseline + safety_buffer;

    let available_for_sandbox = if total_memory > overhead {
        total_memory - overhead
    } else {
        // Fallback if system has very low memory, give it 512MB
        512 * 1024 * 1024
    };

    println!("Memory Probe: Total = {} MB, Safe for Sandbox = {} MB", total_memory / 1024 / 1024, available_for_sandbox / 1024 / 1024);

    MemoryLimits {
        total_memory,
        available_for_sandbox,
    }
}
