# Database Manager Specification

The database manager is the kernel subsystem that provisions, supervises, backs up, restores, and tears down data services used by VLoop.

---

## 1. Managed database classes

| Class | Role |
|---|---|
| SQLite | local file-based workflow/state or lightweight app data |
| Postgres | relational service for richer state and future multi-tenant or advanced querying needs |
| Redis | queue/cache/state acceleration where needed |
| vector store | embeddings and retrieval support |

---

## 2. Responsibilities

- provision local database resources;
- own storage locations and service volumes;
- issue endpoint/capability information to the CP;
- manage lifecycle and health;
- run backup and restore flows;
- coordinate migrations and schema/version tracking.

---

## 3. Local provisioning model

| Engine | Initial local mode |
|---|---|
| SQLite | direct kernel-managed file lifecycle |
| Postgres | Docker-managed local service |
| Redis | Docker-managed local service |
| vector store | kernel-managed local service or library-backed managed data root |

Kubernetes-backed forms come later.

---

## 4. Capability model

The CP should receive:

- a DSN or endpoint reference;
- capability-scoped credentials or connection grants;
- lifecycle metadata.

The CP should not directly own database provisioning.

---

## 5. Backup and restore

The manager should support:

- scheduled and on-demand backups;
- point-in-time or snapshot-style restore where practical;
- safe SQLite backup behavior;
- retention and cleanup rules for backup sets.

---

## 6. Migration rules

- schema/version ownership must be explicit;
- upgrade paths must be repeatable;
- restore and migration interactions must be defined before production use.

---

## 7. Validation requirements

The database manager is complete when:

- the kernel can provision at least SQLite and one service-backed DB locally;
- the CP can consume endpoints via injected config/grants;
- backup/restore is observable and testable;
- teardown rules protect retained data correctly.
