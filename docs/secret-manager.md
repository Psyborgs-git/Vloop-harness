# Secret Manager Specification

The secret manager is the kernel subsystem that stores credentials, issues grants, injects secrets into trusted execution paths, and records audit trails.

---

## 1. Core rule

Secrets are not a normal data-return API. They are managed assets that the kernel grants and injects by capability.

---

## 2. Responsibilities

- store or reference secrets using OS-native secure storage or an encrypted local vault;
- issue scoped grants to workloads or model sessions;
- inject secrets through controlled delivery methods;
- support rotation and revocation;
- maintain audit records of secret use.

---

## 3. Secret classes

| Class | Example |
|---|---|
| model credentials | OpenAI, Azure OpenAI, Anthropic, etc. |
| infrastructure credentials | cloud keys, cluster credentials |
| application secrets | service tokens, database credentials |
| user-specific secrets | personal API keys or access tokens |

---

## 4. Grant model

A secret grant should include:

- the referenced secret;
- target type (workload, model session, service);
- target identity;
- injection method;
- lifetime or expiry;
- audit metadata.

---

## 5. Injection modes

| Mode | Use |
|---|---|
| env injection | workload runtime env |
| file mount | config or certificate file |
| session binding | inference/model session path |

The kernel should choose the safest available mode for the target.

---

## 6. LLM call integration

When the CP needs provider access:

1. it requests a provider/session grant;
2. the kernel validates policy;
3. the kernel injects the secret into the trusted runtime path;
4. the CP uses the granted session context without handling raw secret values directly.

---

## 7. Auditing and rotation

The manager must support:

- secret create/update/delete audit logs;
- grant issuance and revocation audit logs;
- rotation workflows;
- expiry handling;
- redaction in general logs and UI surfaces.

---

## 8. Validation requirements

The secret manager is complete when:

- a workload can receive a needed secret without the CP seeing the raw value;
- an LLM session can authenticate through a kernel grant;
- audit logs are generated for every grant path;
- revoked grants stop working as expected.
