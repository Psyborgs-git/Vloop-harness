import os
from typing import List, Dict, Any
from core.ports import IVectorStore

class DummyVectorStoreAdapter(IVectorStore):
    """
    A temporary dummy adapter for vector storage since onnxruntime 
    isn't available for chromadb on this macOS architecture right now.
    """
    def __init__(self, persist_directory: str):
        self.persist_directory = persist_directory
        self.storage = {}

    def add_document(self, collection_name: str, document_id: str, text: str, metadata: Dict[str, Any] = None) -> None:
        if collection_name not in self.storage:
            self.storage[collection_name] = []
        
        self.storage[collection_name].append({
            "id": document_id,
            "text": text,
            "metadata": metadata or {}
        })

    def search(self, collection_name: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        # In a real implementation, this would compute embeddings and do cosine similarity
        if collection_name not in self.storage:
            return []
        
        # Dummy "search": just return the first top_k
        return self.storage[collection_name][:top_k]
