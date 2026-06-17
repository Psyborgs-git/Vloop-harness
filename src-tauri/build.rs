fn main() -> Result<(), Box<dyn std::error::Error>> {
    tauri_build::build();
    tonic_build::configure().compile_protos(&["../proto/system.proto"], &["../proto"])?;
    Ok(())
}
