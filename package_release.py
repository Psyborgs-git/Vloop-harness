#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
import platform

def run_cmd(args, cwd=None):
    print(f"Running: {' '.join(args)} in {cwd or os.getcwd()}")
    res = subprocess.run(args, cwd=cwd)
    if res.returncode != 0:
        print(f"Error running {' '.join(args)}")
        sys.exit(res.returncode)

def build_frontend():
    print("--- Building React Frontend ---")
    react_dir = os.path.abspath("react")
    run_cmd(["npm", "install"], cwd=react_dir)
    run_cmd(["npm", "run", "build"], cwd=react_dir)

def build_rust():
    print("--- Building Rust Core CLI ---")
    rust_dir = os.path.abspath("harness-core")
    run_cmd(["cargo", "build", "--release"], cwd=rust_dir)

def package():
    print("--- Packaging Release Distribution ---")
    os_name = platform.system().lower()
    arch = platform.machine().lower()
    dist_dir = os.path.abspath("dist")
    
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    os.makedirs(dist_dir)

    target_name = f"vloop-harness-{os_name}-{arch}"
    release_dir = os.path.join(dist_dir, target_name)
    os.makedirs(release_dir)

    # 1. Copy source / asset directories
    shutil.copytree("harness", os.path.join(release_dir, "harness"))
    shutil.copytree("react/dist", os.path.join(release_dir, "react/dist"))
    shutil.copy("pyproject.toml", os.path.join(release_dir, "pyproject.toml"))
    shutil.copy("uv.lock", os.path.join(release_dir, "uv.lock"))

    # 2. Copy compiled binary
    binary_ext = ".exe" if os_name == "windows" else ""
    src_bin = os.path.join("harness-core", "target", "release", f"vloop-harness{binary_ext}")
    dest_bin = os.path.join(release_dir, f"vloop-harness{binary_ext}")
    
    if not os.path.exists(src_bin):
        print(f"Compiled binary not found at {src_bin}")
        sys.exit(1)
        
    shutil.copy(src_bin, dest_bin)
    os.chmod(dest_bin, 0o755)

    print(f"Created standard directory release package at: {release_dir}")

    # 3. If macOS, create .app bundle
    if os_name == "darwin":
        print("--- Packaging macOS App Bundle (VloopHarness.app) ---")
        app_dir = os.path.join(dist_dir, "VloopHarness.app")
        contents_dir = os.path.join(app_dir, "Contents")
        macos_dir = os.path.join(contents_dir, "MacOS")
        resources_dir = os.path.join(contents_dir, "Resources")

        os.makedirs(macos_dir, exist_ok=True)
        os.makedirs(resources_dir, exist_ok=True)

        # Write Info.plist
        plist_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>vloop-harness</string>
    <key>CFBundleIdentifier</key>
    <string>com.vloop.harness</string>
    <key>CFBundleName</key>
    <string>VloopHarness</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>0.2.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
"""
        with open(os.path.join(contents_dir, "Info.plist"), "w") as f:
            f.write(plist_content)

        # Copy executable to MacOS
        shutil.copy(src_bin, os.path.join(macos_dir, "vloop-harness"))
        os.chmod(os.path.join(macos_dir, "vloop-harness"), 0o755)

        # Copy assets and code to Resources
        shutil.copytree("harness", os.path.join(resources_dir, "harness"))
        shutil.copytree("react/dist", os.path.join(resources_dir, "react/dist"))
        shutil.copy("pyproject.toml", os.path.join(resources_dir, "pyproject.toml"))
        shutil.copy("uv.lock", os.path.join(resources_dir, "uv.lock"))

        print(f"Created VloopHarness.app bundle at: {app_dir}")

if __name__ == "__main__":
    build_frontend()
    build_rust()
    package()
    print("--- Build and Packaging complete! ---")
