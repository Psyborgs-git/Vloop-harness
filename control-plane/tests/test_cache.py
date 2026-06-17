import pytest
import shutil
import tempfile
import os
from core.cache import SemanticCacheInterceptor
from adapters.dummy_vector import DummyVectorStoreAdapter

@pytest.fixture
def temp_vec_path():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)

def test_semantic_cache_miss_when_empty(temp_vec_path):
    store = DummyVectorStoreAdapter(temp_vec_path)
    cache = SemanticCacheInterceptor(store)
    
    messages = [{"role": "user", "content": "hello world"}]
    # Should be a cache miss
    result = cache.check_cache(messages, {})
    assert result is None

def test_semantic_cache_hit_after_update(temp_vec_path):
    store = DummyVectorStoreAdapter(temp_vec_path)
    cache = SemanticCacheInterceptor(store)
    
    messages = [{"role": "user", "content": "calculate 2+2"}]
    response_text = "The answer is 4."
    
    # Update cache
    cache.update_cache(messages, response_text)
    
    # Check cache (exact hit)
    result = cache.check_cache(messages, {})
    assert result == response_text

def test_semantic_cache_semantic_hit(temp_vec_path):
    store = DummyVectorStoreAdapter(temp_vec_path)
    cache = SemanticCacheInterceptor(store, threshold=0.90)
    
    messages = [{"role": "user", "content": "calculate 2+2"}]
    response_text = "The answer is 4."
    
    # Manually add a document with score >= threshold to test semantic hit logic
    import uuid
    store.add_document(
        collection_name="semantic_cache",
        document_id=str(uuid.uuid4()),
        text=response_text,
        metadata={"hash": "different_hash", "original_prompt": "calculate 2+2", "score": 0.95}
    )
    
    # Should trigger semantic hit even though the prompt hash is different because our semantic check
    # will see score 0.95 >= threshold 0.90
    result = cache.check_cache(messages, {})
    assert result == response_text
