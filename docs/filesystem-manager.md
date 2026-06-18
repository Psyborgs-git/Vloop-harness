# Filesystem Manager Specification

The filesystem manager is the kernel subsystem that owns all persistent and ephemeral file boundaries used by VLoop.

---

## 1. Responsibilities

- create and manage runtime directory structure;
- provision workspaces and reusable volumes;
- manage artifacts and logs;
- enforce path policy and mount safety;
- perform safe archive extraction;
- apply cleanup and retention rules.

---

## 2. Directory model

Recommended root: `~/.vloop/`

| Path | Role |
|---|---|
| `run/` | IPC and process runtime files |
| `state/` | durable state and reconciliation metadata |
| `workspaces/` | per-workflow managed workspaces |
| `volumes/` | reusable or service-scoped volumes |
| `artifacts/` | persisted workflow outputs |
| `logs/` | system and workflow logs |
| `db/` | local database files |
| `cache/` | dependency or image caches |

---

## 3. Workspace lifecycle

1. create workspace from a kernel request;
2. attach to workloads by workspace ID, not arbitrary path;
3. preserve requested artifacts;
4. clean up according to retention policy.

---

## 4. Volume classes

| Volume type | Example use |
|---|---|
| ephemeral workspace volume | task-local execution |
| persisted service volume | Postgres/Redis/vector store data |
| shared artifact volume | preview or output exchange |

---

## 5. Safety requirements

- canonicalize paths before use;
- reject unsafe path traversal;
- reject symlink-based escape patterns;
- use safe archive extraction;
- isolate managed paths from arbitrary host paths;
- support locks where concurrent access matters.

---

## 6. Cleanup and retention

The manager should implement:

- immediate cleanup for fully ephemeral resources;
- retention-based cleanup for artifacts and logs;
- garbage collection for abandoned workspaces;
- safe cleanup sequencing for resources still attached to workloads or databases.

---

## 7. Validation requirements

The filesystem manager is complete when:

- workloads mount managed paths only;
- archive extraction is safe;
- artifacts survive according to policy;
- garbage collection cannot silently delete active resources.
