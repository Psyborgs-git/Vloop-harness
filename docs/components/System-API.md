# System API

## Overview
Rust module for probing local hardware capabilities.

## Responsibilities
- Calculates safe execution limits for local Docker sandboxes.
- Formula: `Available_RAM = Total_RAM - (OS_Baseline + Rust_Overhead + Safety_Buffer)`.

## Interactions
- **FS Manager**: Passes calculated limits to be written into `active.toml`.
