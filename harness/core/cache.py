"""
Caching module for VLoop Harness.

Supports in-memory caching with optional Redis backend for distributed scenarios.
"""

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    """Cache entry with expiration."""
    
    value: Any
    expires_at: float | None = None
    
    def is_expired(self) -> bool:
        """Check if the entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class Cache:
    """Simple in-memory cache with TTL support."""
    
    def __init__(self):
        self._store: dict[str, CacheEntry] = {}
    
    def get(self, key: str) -> Any | None:
        """Get a value from the cache."""
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._store[key]
            return None
        return entry.value
    
    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Set a value in the cache with optional TTL."""
        expires_at = None
        if ttl_seconds is not None:
            expires_at = time.time() + ttl_seconds
        
        self._store[key] = CacheEntry(value=value, expires_at=expires_at)
    
    def delete(self, key: str) -> bool:
        """Delete a value from the cache."""
        if key in self._store:
            del self._store[key]
            return True
        return False
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self._store.clear()
    
    def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from the cache."""
        result = {}
        for key in keys:
            value = self.get(key)
            if value is not None:
                result[key] = value
        return result
    
    def set_many(self, mapping: dict[str, Any], ttl_seconds: int | None = None) -> None:
        """Set multiple values in the cache."""
        for key, value in mapping.items():
            self.set(key, value, ttl_seconds)
    
    def delete_many(self, keys: list[str]) -> int:
        """Delete multiple values from the cache."""
        deleted = 0
        for key in keys:
            if self.delete(key):
                deleted += 1
        return deleted
    
    def cleanup_expired(self) -> int:
        """Remove all expired entries."""
        now = time.time()
        expired_keys = [
            key for key, entry in self._store.items()
            if entry.expires_at is not None and entry.expires_at < now
        ]
        for key in expired_keys:
            del self._store[key]
        return len(expired_keys)
    
    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = len(self._store)
        expired = self.cleanup_expired()
        return {
            "total_entries": total,
            "expired_entries": expired,
            "active_entries": total - expired,
        }


class CacheManager:
    """Manages multiple cache namespaces."""
    
    def __init__(self):
        self._caches: dict[str, Cache] = {}
    
    def get_cache(self, namespace: str) -> Cache:
        """Get or create a cache for a namespace."""
        if namespace not in self._caches:
            self._caches[namespace] = Cache()
        return self._caches[namespace]
    
    def clear_namespace(self, namespace: str) -> None:
        """Clear all entries in a namespace."""
        if namespace in self._caches:
            self._caches[namespace].clear()
    
    def clear_all(self) -> None:
        """Clear all namespaces."""
        for cache in self._caches.values():
            cache.clear()
    
    def get_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all namespaces."""
        return {
            namespace: cache.stats()
            for namespace, cache in self._caches.items()
        }


# Global cache manager instance
_cache_manager: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    """Get the global cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


def get_cache(namespace: str = "default") -> Cache:
    """Get a cache for a specific namespace."""
    return get_cache_manager().get_cache(namespace)


# Common cache namespaces
CACHE_NAMESPACES = {
    "components": "components",
    "agent_runs": "agent_runs",
    "providers": "providers",
    "app_manifests": "app_manifests",
    "views": "views",
    "api_responses": "api_responses",
}


def cache_component(component_id: str, component_data: dict, ttl_seconds: int = 3600) -> None:
    """Cache a component."""
    cache = get_cache(CACHE_NAMESPACES["components"])
    cache.set(f"component:{component_id}", component_data, ttl_seconds)


def get_cached_component(component_id: str) -> dict | None:
    """Get a cached component."""
    cache = get_cache(CACHE_NAMESPACES["components"])
    return cache.get(f"component:{component_id}")


def cache_agent_run(run_id: str, run_data: dict, ttl_seconds: int = 1800) -> None:
    """Cache an agent run."""
    cache = get_cache(CACHE_NAMESPACES["agent_runs"])
    cache.set(f"run:{run_id}", run_data, ttl_seconds)


def get_cached_agent_run(run_id: str) -> dict | None:
    """Get a cached agent run."""
    cache = get_cache(CACHE_NAMESPACES["agent_runs"])
    return cache.get(f"run:{run_id}")


def cache_provider(provider_id: str, provider_data: dict, ttl_seconds: int = 7200) -> None:
    """Cache a provider."""
    cache = get_cache(CACHE_NAMESPACES["providers"])
    cache.set(f"provider:{provider_id}", provider_data, ttl_seconds)


def get_cached_provider(provider_id: str) -> dict | None:
    """Get a cached provider."""
    cache = get_cache(CACHE_NAMESPACES["providers"])
    return cache.get(f"provider:{provider_id}")


def cache_api_response(cache_key: str, response_data: Any, ttl_seconds: int = 300) -> None:
    """Cache an API response."""
    cache = get_cache(CACHE_NAMESPACES["api_responses"])
    cache.set(f"api:{cache_key}", response_data, ttl_seconds)


def get_cached_api_response(cache_key: str) -> Any | None:
    """Get a cached API response."""
    cache = get_cache(CACHE_NAMESPACES["api_responses"])
    return cache.get(f"api:{cache_key}")
