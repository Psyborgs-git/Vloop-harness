# Kubernetes Backend Specification

Kubernetes is the first expansion backend after local Docker orchestration is stable. It extends the same kernel-owned workload model into cluster execution.

---

## 1. Purpose

The Kubernetes backend allows `vloopd` to map workload intent onto cluster resources while preserving the same CP-facing abstractions used for local Docker execution.

---

## 2. Responsibilities

- translate workload specs into Kubernetes resources;
- manage namespaces, labels, ownership, and cleanup;
- watch pod/job status and stream logs/events back to the CP through kernel APIs;
- expose service endpoints and preview URLs where appropriate;
- provision or bind supporting services using the same kernel resource model.

---

## 3. Initial resource targets

| Workload type | Likely K8s resource |
|---|---|
| worker | Job or Pod |
| preview | Deployment/Pod + Service |
| long-lived service | Deployment/StatefulSet + Service |
| support database | StatefulSet or managed external service reference |

---

## 4. Design rules

- CP should not see Kubernetes-specific complexity unless explicitly needed for diagnostics;
- kernel workload IDs remain the primary identity;
- status/log/event behavior should mirror local Docker semantics as closely as possible;
- cleanup and ownership labels must be explicit.

---

## 5. Security and policy

The backend should assume:

- namespace scoping for VLoop-managed resources;
- explicit RBAC requirements;
- controlled secret injection paths;
- careful route/service exposure.

---

## 6. Completion criteria

This backend is complete when the same CP workload request can be satisfied by either Docker or Kubernetes without changing CP workflow logic.
