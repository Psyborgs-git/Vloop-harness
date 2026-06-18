use anyhow::Result;
use tracing::info;

fn print_help() {
    eprintln!("vloopctl <command>\nCommands: install-service | uninstall-service | start | stop | restart | status | open-ui | logs | doctor");
}

fn main() -> Result<()> {
    tracing_subscriber::fmt::init();

    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        print_help();
        return Ok(());
    }

    let cmd = args[1].as_str();
    info!("vloopctl: requested command {} (stub)", cmd);

    // TODO: implement OS service calls.
    Ok(())
}
