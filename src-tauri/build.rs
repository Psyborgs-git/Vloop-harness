fn main() {
    tonic_build::compile_protos("../proto/sandbox.proto")
        .unwrap_or_else(|e| panic!("Failed to compile sandbox.proto: {}", e));
    tonic_build::compile_protos("../proto/process.proto")
        .unwrap_or_else(|e| panic!("Failed to compile process.proto: {}", e));
    tauri_build::build()
}
