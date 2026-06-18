# Packaging and Distribution Specification

VLoop is distributed as a native product, not a developer-only source bundle. Packaging must make the daemon/service model feel like a normal desktop installation.

---

## 1. Installed product contents

Every platform package should include:

- `vloopd`
- `vloopctl`
- `vloop-launcher`
- Python Control Plane runtime/assets
- React static UI bundle
- service registration assets
- uninstall and upgrade metadata

---

## 2. Platform targets

| OS | Target packaging model |
|---|---|
| macOS | signed/notarized `.pkg` or `.dmg` with LaunchAgent and launcher integration |
| Windows | MSI/MSIX with Windows Service support and scheduled-task fallback |
| Linux | `.deb`/`.rpm` with systemd user service and desktop entry |

---

## 3. Packaging responsibilities

Packaging must:

- install binaries and runtime assets into stable locations;
- register the service/agent/task correctly;
- create normal launch entrypoints;
- support upgrade without corrupting user data;
- support uninstall without leaving critical service residue.

---

## 4. Upgrade behavior

Upgrades should preserve:

- managed runtime directories and user data;
- service registration semantics;
- compatibility checks between kernel, CP, and UI bundle.

Rollback behavior should be defined before production release.

---

## 5. Signing and trust

Packaging should support:

- macOS signing and notarization;
- Windows signing where required;
- Linux package metadata and repository compatibility as needed.

---

## 6. Release pipeline expectations

A release pipeline should build:

- kernel binaries for target platforms;
- Python CP runtime bundle/assets;
- frontend static bundle;
- platform-native packages;
- smoke-test artifacts.

---

## 7. Validation requirements

Packaging is complete when:

- install, launch, restart, and uninstall work on all target platforms;
- the user never has to find or run the daemon manually;
- service registration is stable across upgrades.
