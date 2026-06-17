# LiteFS Sync

## Overview
Rust module for distributed SQLite synchronization.

## Responsibilities
- If VLoop is deployed in a distributed/clustered environment, this module interfaces with LiteFS to replicate the `.sqlite` databases across nodes.
