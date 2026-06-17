# RemoteK8sAdapter

## Overview
Implements `IExecutionManager` for Kubernetes clusters.

## Responsibilities
- Uses the Python Kubernetes SDK to dispatch `BatchV1Api` Jobs to remote clusters (EKS, GKE, K3s).
