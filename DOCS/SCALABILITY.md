# Scalability and Performance Guide

This guide covers scaling VLoop Harness for production workloads.

## Horizontal Scaling

### Architecture

VLoop Harness can be scaled horizontally by running multiple backend instances behind a load balancer.

```
                    Load Balancer
                         |
        +----------------+----------------+
        |                |                |
   Instance 1       Instance 2       Instance 3
   (Backend)        (Backend)        (Backend)
        |                |                |
        +----------------+----------------+
                         |
                   Shared Database
                   (PostgreSQL)
```

### Load Balancer Configuration

#### Nginx Configuration

```nginx
upstream vloop_backend {
    least_conn;
    server backend1:8000;
    server backend2:8000;
    server backend3:8000;
}

server {
    listen 80;
    server_name api.vloop-harness.com;

    location / {
        proxy_pass http://vloop_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Using Docker Compose

```yaml
version: '3.8'
services:
  backend:
    image: vloop-harness:latest
    deploy:
      replicas: 3
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/vloop
    depends_on:
      - postgres
  
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=vloop
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - backend

volumes:
  postgres_data:
```

### Session Management

For horizontal scaling, use a shared session store:

#### Redis for Sessions

```python
# In harness/core/session.py
import redis
from fastapi_sessions.backends import InMemoryBackend

redis_client = redis.Redis(host='redis', port=6379, db=0)
session_backend = InMemoryBackend(redis_client)
```

### Database Connection Pooling

Configure connection pooling for PostgreSQL:

```python
# In harness/data/db.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
```

## Caching Strategy

### In-Memory Caching

Use the built-in cache module for frequently accessed data:

```python
from harness.core.cache import cache_component, get_cached_component

# Cache a component
cache_component(component_id, component_data, ttl_seconds=3600)

# Retrieve from cache
cached = get_cached_component(component_id)
```

### Redis Caching (Optional)

For distributed caching, integrate Redis:

```python
import redis
import json

class RedisCache:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def get(self, key: str) -> Optional[Any]:
        data = self.redis.get(key)
        if data:
            return json.loads(data)
        return None
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        self.redis.setex(key, ttl, json.dumps(value))
```

### Cache Invalidation

Implement cache invalidation strategies:

- **Time-based**: Use TTL for automatic expiration
- **Event-based**: Invalidate on data changes
- **Manual**: Provide admin endpoints for cache clearing

```python
# Invalidate component cache on update
def update_component(component_id: str, data: dict):
    # Update database
    db.update_component(component_id, data)
    # Invalidate cache
    cache = get_cache("components")
    cache.delete(f"component:{component_id}")
```

## Performance Optimization

### Database Optimization

#### Indexing

```sql
-- Common query indexes
CREATE INDEX idx_agent_runs_status ON agent_runs(status);
CREATE INDEX idx_agent_runs_created_at ON agent_runs(created_at DESC);
CREATE INDEX idx_tool_traces_run_id ON tool_traces(run_id);
CREATE INDEX idx_components_name ON components(name);
CREATE INDEX idx_chat_sessions_user_id ON chat_sessions(user_id);
```

#### Query Optimization

```python
# Use select_related for joins
from sqlalchemy.orm import selectinload

query = (
    select(AgentRun)
    .options(selectinload(AgentRun.steps))
    .where(AgentRun.status == "running")
)
```

### Backend Optimization

#### Async Operations

Ensure all I/O operations are async:

```python
# Good - async
async def get_component(component_id: str):
    return await db.execute(select(Component).where(Component.id == component_id))

# Bad - sync
def get_component(component_id: str):
    return db.execute(select(Component).where(Component.id == component_id))
```

#### Response Compression

Enable Gzip compression:

```python
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)
```

### Frontend Optimization

#### Code Splitting

```typescript
// Lazy load components
const ContextualPanel = lazy(() => import('./ContextualPanel'));
const WorkspaceArea = lazy(() => import('./WorkspaceArea'));
```

#### Bundle Optimization

```javascript
// vite.config.ts
export default {
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          mui: ['@mui/material', '@mui/icons-material'],
        },
      },
    },
  },
}
```

## Resource Limits

### Memory Limits

Set memory limits for containers:

```yaml
# docker-compose.yml
services:
  backend:
    image: vloop-harness:latest
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
```

### CPU Limits

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2.0'
        reservations:
          cpus: '1.0'
```

### Worker Processes

Configure multiple workers:

```python
# In harness/main.py
import uvicorn

uvicorn.run(
    "harness.server.app:app",
    host="0.0.0.0",
    port=8000,
    workers=4,  # Number of worker processes
)
```

## Monitoring

### Performance Metrics

Monitor key metrics:
- Request latency (p50, p95, p99)
- Request rate (requests per second)
- Error rate
- Database query time
- Cache hit rate
- Memory usage
- CPU usage

### Alerting

Set up alerts for:
- High error rate (> 5%)
- High latency (p95 > 1s)
- Low cache hit rate (< 50%)
- High memory usage (> 80%)
- High CPU usage (> 80%)

## Load Testing

### Using Locust

```python
# locustfile.py
from locust import HttpUser, task, between

class VLoopUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def list_components(self):
        self.client.get("/api/components")
    
    @task
    def get_agent_runs(self):
        self.client.get("/api/agent-runs")
```

Run load test:
```bash
locust -f locustfile.py --host=http://localhost:8000
```

### Using k6

```javascript
// load-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export default function() {
  let res = http.get('http://localhost:8000/api/components');
  check(res, { 'status was 200': (r) => r.status == 200 });
  sleep(1);
}
```

Run load test:
```bash
k6 run load-test.js
```

## Scaling Checklist

- [ ] Configure load balancer
- [ ] Set up shared database (PostgreSQL)
- [ ] Configure connection pooling
- [ ] Implement distributed caching (Redis)
- [ ] Set up session management
- [ ] Configure worker processes
- [ ] Set resource limits
- [ ] Implement monitoring
- [ ] Configure alerting
- [ ] Run load tests
- [ ] Document scaling procedures
