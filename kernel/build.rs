fn main() {
    // TODO: compile proto/kernel.proto and proto/control_plane.proto.
    println!("cargo:rerun-if-changed=../proto/kernel.proto");
    println!("cargo:rerun-if-changed=../proto/control_plane.proto");
}
