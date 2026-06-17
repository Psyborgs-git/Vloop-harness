import hashlib
import json

class SemanticCacheInterceptor:
    def __init__(self, vector_store, threshold=0.95):
        self.vector_store = vector_store
        self.threshold = threshold

    def _hash_prompt(self, messages):
        # Create a stable string representation of the prompt messages
        prompt_str = json.dumps(messages, sort_keys=True)
        return hashlib.sha256(prompt_str.encode('utf-8')).hexdigest()

    def check_cache(self, messages, kwargs):
        """
        Check if the prompt has a semantic match in the vector store.
        """
        prompt_hash = self._hash_prompt(messages)
        prompt_text = "\n".join([m.get("content", "") for m in messages])
        
        # 1. Exact hash check (fastest)
        try:
            exact_matches = self.vector_store.search(
                collection_name="semantic_cache",
                query=prompt_text,
                top_k=5
            )
            for match in exact_matches:
                metadata = match.get("metadata", {})
                if metadata.get("hash") == prompt_hash:
                    print(f"Exact cache hit for prompt {prompt_hash[:8]}...")
                    return match["text"]
        except Exception as e:
            print(f"Exact cache check failed: {e}")
            pass

        # 2. Semantic Similarity Check
        try:
            semantic_matches = self.vector_store.search(
                collection_name="semantic_cache",
                query=prompt_text,
                top_k=1
            )
            if semantic_matches and len(semantic_matches) > 0:
                match = semantic_matches[0]
                metadata = match.get("metadata", {})
                score = metadata.get("score", 1.0)  # Default to 1.0 if not present in dummy
                if score >= self.threshold:
                    print(f"Semantic cache hit (score: {score:.2f}) for prompt {prompt_hash[:8]}...")
                    return match["text"]
        except Exception as e:
            print(f"Semantic cache search failed: {e}")
            pass
            
        return None

    def update_cache(self, messages, response_text):
        """
        Store a successful response in the vector store for future cache hits.
        """
        prompt_hash = self._hash_prompt(messages)
        prompt_text = "\n".join([m.get("content", "") for m in messages])
        
        try:
            import uuid
            self.vector_store.add_document(
                collection_name="semantic_cache",
                document_id=str(uuid.uuid4()),
                text=response_text,
                metadata={"hash": prompt_hash, "original_prompt": prompt_text, "score": 1.0}
            )
        except Exception as e:
            print(f"Failed to update semantic cache: {e}")
