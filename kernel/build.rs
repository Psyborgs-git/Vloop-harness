fn main() {
    let protoc = protoc_bin_vendored::protoc_bin_path().expect("failed to locate vendored protoc");
    std::env::set_var("PROTOC", protoc);

    println!("cargo:rerun-if-changed=../proto/kernel.proto");
    println!("cargo:rerun-if-changed=../proto/control_plane.proto");

    tonic_build::configure()
        .build_server(true)
        .build_client(true)
        .compile_protos(
            &["../proto/kernel.proto", "../proto/control_plane.proto"],
            &["../proto"],
        )
        .expect("failed to compile VLoop proto definitions");
}
