# FS Manager

## Overview
Rust module governing the `~/.vloop/` filesystem boundary.

## Responsibilities
- Ensures strict structural integrity of the local state directories to prevent cross-OS corruption.
- Writes the `active.toml` configuration file before the Python process boots.

## Interactions
- **Python CP**: Python reads `active.toml` on boot to configure its adapters.
