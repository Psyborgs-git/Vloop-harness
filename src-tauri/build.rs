fn main() {
    let protos = [
        "../proto/sandbox.proto",
        "../proto/process.proto",
        "../proto/vault.proto",
        "../proto/terminal.proto",
        "../proto/system.proto",
        "../proto/environment.proto",
    ];
    for proto in protos {
        tonic_build::compile_protos(proto)
            .unwrap_or_else(|e| panic!("Failed to compile {}: {}", proto, e));
    }
    tauri_build::build()
}
