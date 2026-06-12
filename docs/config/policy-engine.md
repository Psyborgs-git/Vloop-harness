# Policy Engine

The `policy.json` (or equivalent SQLite configuration) defines the rules the Rust Kernel enforces on all sandboxes.

## Schema

```json
{
  "blacklisted_commands": ["rm -rf /", "mkfs"],
  "resource_quotas": {
    "docker": {
      "max_cpu": "2.0",
      "max_ram": "2g"
    },
    "local": {
      "max_ram": "4g"
    }
  },
  "timeout_thresholds": {
    "default_ms": 300000,
    "max_idle_ms": 60000
  }
}
```

The Rust Kernel validates every `ProvisionRequest` against these rules. If a rule is violated, the provisioning is rejected instantly.
