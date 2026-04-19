# Deployment Guide

## macOS

### Requirements
- Rust (via rustup), Node 20+, Python 3.11+, Xcode Command Line Tools

### Build
```bash
./scripts/setup.sh
./scripts/build-all.sh
```
Bundle output: `harness-core/target/release/bundle/dmg/`

### Tauri Entitlements (macOS)
The `tauri.conf.json` includes:
- `com.apple.security.network.client` — outbound HTTP to Ollama
- `com.apple.security.files.all` — file system access for VFS

## Linux

### Requirements
```bash
sudo apt-get install libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf libsqlite3-dev
```

### inotify Limits
For the file watcher (`notify` crate), increase inotify limits if watching large project trees:
```bash
echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Build
```bash
./scripts/setup.sh && ./scripts/build-all.sh
```
Bundle: `harness-core/target/release/bundle/appimage/`

## Windows

### Requirements
- [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with C++ workload
- WebView2 (bundled with Windows 11, or install from Microsoft)
- Node 20+, Python 3.11+

### PTY Note (R1)
ConPTY is used via `portable-pty`. Tested with PowerShell and CMD. For WSL shells, ensure WSL is installed.

### git2 Note (R3)
If git2/libgit2 compilation fails, set environment variable:
```
LIBGIT2_SYS_USE_PKG_CONFIG=0
```
Or ensure OpenSSL is installed via vcpkg.

### Build
```powershell
.\scripts\setup.sh  # Use Git Bash
cargo tauri build
```
Bundle: `harness-core\target\release\bundle\msi\`

## Docker (inference-backend only)

```bash
cd inference-backend
docker compose up -d
```

This starts the inference-backend with Ollama proxy support.

## Environment Variables

Copy `inference-backend/.env.example` to `inference-backend/.env` and configure:

```env
LM_PROVIDER=ollama          # ollama|openai|anthropic|lmstudio
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
HARNESS_CORE_URL=http://localhost:47200
PORT=47201
SANDBOX_MODE=process         # process|docker
DB_ENGINE=sqlite             # sqlite|postgres
```

## LAN QR Access (Milestone 11)

1. Start the app and click **Host Service** in the sidebar
2. Click **Start Host** — Axum binds `:47299` on all interfaces
3. Scan the QR code from any device on the same LAN
4. Token is one-time-use with 15-minute expiry
5. Click **Rotate Token** to generate a new QR
