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
        # Assuming the vector store can do metadata filtering on 'hash'
        try:
            exact_matches = self.vector_store.search(
                query_text="", 
                filter_metadata={"hash": prompt_hash},
                limit=1
            )
            if exact_matches and len(exact_matches) > 0:
                print(f"Exact cache hit for prompt {prompt_hash[:8]}...")
                return exact_matches[0]["content"]
        except Exception:
            pass

        # 2. Semantic Similarity Check
        try:
            semantic_matches = self.vector_store.search(
                query_text=prompt_text,
                limit=1
            )
            if semantic_matches and len(semantic_matches) > 0:
                match = semantic_matches[0]
                if match.get("score", 0) >= self.threshold:
                    print(f"Semantic cache hit (score: {match.get('score', 0):.2f}) for prompt {prompt_hash[:8]}...")
                    return match["content"]
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
            self.vector_store.add_document(
                content=response_text,
                metadata={"hash": prompt_hash, "original_prompt": prompt_text}
            )
        except Exception as e:
            print(f"Failed to update semantic cache: {e}")
