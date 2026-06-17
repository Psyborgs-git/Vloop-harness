# DummyVectorStoreAdapter

## Overview
Implements `IVectorStore` as a temporary in-memory fallback.

## Responsibilities
- Stores vectors in a Python dictionary. Used when native binary dependencies (like ChromaDB's ONNX runtime) are unavailable on the host architecture.
