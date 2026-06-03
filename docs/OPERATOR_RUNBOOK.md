# VLoop Harness - Operator Runbook

This runbook provides operational guidance for running and maintaining VLoop Harness in production.

## Table of Contents
- [System Overview](#system-overview)
- [Startup and Shutdown](#startup-and-shutdown)
- [Health Monitoring](#health-monitoring)
- [Common Operations](#common-operations)
- [Troubleshooting](#troubleshooting)
- [Backup and Recovery](#backup-and-recovery)
- [Performance Tuning](#performance-tuning)

## System Overview

VLoop Harness consists of:
- **Backend**: Python FastAPI server with DSPy integration
- **Frontend**: React dashboard with workspace mode
- **Database**: SQLite (default) or PostgreSQL
- **AI Providers**: Anthropic, OpenAI, Ollama
- **Tools**: Terminal, Filesystem, Browser, Database

### Architecture
```
React UI → FastAPI Backend → DSPy Engine → AI Providers
                ↓
          SQLite/PostgreSQL
                ↓
          Tool Runtime (Terminal, Filesystem, Browser, Database)
```

## Startup and Shutdown

### Starting the System

#### Development Mode
```bash
# Start backend
cd /path/to/Vloop-harness
python -m harness.main

# Start frontend (in separate terminal)
cd react
npm run dev
```

#### Production Mode
```bash
# Using systemd (Linux)
sudo systemctl start vloop-harness
sudo systemctl start vloop-harness-frontend

# Using Docker
docker-compose up -d
```

### Stopping the System

#### Development Mode
- Press Ctrl+C in both terminal windows
- Or kill processes: `pkill -f "python -m harness.main"` and `pkill -f "vite"`

#### Production Mode
```bash
# systemd
sudo systemctl stop vloop-harness
sudo systemctl stop vloop-harness-frontend

# Docker
docker-compose down
```

## Health Monitoring

### Health Checks

#### Backend Health
```bash
# Check if backend is running
curl http://localhost:8000/health

# Expected response: {"status": "ok"}
```

#### Frontend Health
```bash
# Check if frontend is accessible
curl http://localhost:5173

# Expected: HTML response
```

#### Database Health
```bash
# Check database file exists (SQLite)
ls -lh .harness/harness.db

# Check PostgreSQL connection
psql -h localhost -U vloop -d vloop -c "SELECT 1;"
```

### Monitoring Endpoints

- `/api/metrics` - System metrics (CPU, memory, disk, process count)
- `/api/alerts` - Active alerts
- `/api/agent-runs` - Agent run status
- `/api/providers` - AI provider status

### Log Locations

- **Backend logs**: `.harness/logs/` (per-component ring buffers)
- **Frontend logs**: Browser console (development) or server logs (production)
- **System logs**: `/var/log/vloop-harness/` (production)

## Common Operations

### Managing AI Providers

#### Add a New Provider
```bash
# Via API
curl -X POST http://localhost:8000/api/providers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "anthropic",
    "provider_type": "anthropic",
    "api_key": "your-api-key",
    "model": "claude-3-sonnet-20240229",
    "is_default": true
  }'
```

#### Test Provider Connection
```bash
curl http://localhost:8000/api/providers/{provider_id}/test
```

### Managing Agent Runs

#### Start an Agent Run
```bash
curl -X POST http://localhost:8000/api/agent-runs \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Create a new component",
    "autonomy_mode": "suggest",
    "context": "Additional context"
  }'
```

#### Cancel a Running Agent
```bash
curl -X POST http://localhost:8000/api/agent-runs/{run_id}/cancel
```

#### Resume a Paused Agent
```bash
curl -X POST http://localhost:8000/api/agent-runs/{run_id}/resume
```

### Managing Components

#### List Components
```bash
curl http://localhost:8000/api/components
```

#### Validate a Component
```bash
curl -X POST http://localhost:8000/api/components/{component_id}/validate
```

#### Run Smoke Tests
```bash
curl -X POST http://localhost:8000/api/components/{component_id}/smoke-test
```

### Managing App Manifests

#### Create an App from Spec
```bash
curl -X POST http://localhost:8000/api/apps/generate \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-app",
    "description": "My application",
    "backend_type": "component",
    "backend_logic": "def run(): pass",
    "frontend_views": [{"name": "MainView", "type": "form"}],
    "state_schema": {"counter": 0},
    "permissions": ["read"]
  }'
```

#### Promote an App
```bash
curl -X POST http://localhost:8000/api/apps/{app_id}/promote \
  -H "Content-Type: application/json" \
  -d '{"status": "active"}'
```

## Troubleshooting

### Backend Won't Start

#### Symptom: Backend fails to start with port error
**Solution**: Check if port 8000 is already in use
```bash
lsof -i :8000
# Kill the process or change port in .env
```

#### Symptom: Database connection error
**Solution**: Verify database file exists and is writable
```bash
ls -la .harness/harness.db
chmod 644 .harness/harness.db
```

### Agent Runs Stuck

#### Symptom: Agent run in "running" state but not progressing
**Solution**: Check agent logs and cancel if needed
```bash
# Check logs
cat .harness/logs/agent.log

# Cancel the run
curl -X POST http://localhost:8000/api/agent-runs/{run_id}/cancel
```

#### Symptom: Agent run fails with "tool execution error"
**Solution**: Check tool permissions and workspace boundaries
```bash
# Verify tool policies
curl http://localhost:8000/api/tools/policies

# Check workspace directory
ls -la .harness/workspace/
```

### High Memory Usage

#### Symptom: System memory usage > 80%
**Solution**: Check resource metrics and restart if needed
```bash
# Check metrics
curl http://localhost:8000/api/metrics/resource

# Restart backend
sudo systemctl restart vloop-harness
```

### AI Provider Errors

#### Symptom: Provider returns authentication errors
**Solution**: Verify API key and provider configuration
```bash
# Check provider status
curl http://localhost:8000/api/providers

# Update provider with correct API key
curl -X PUT http://localhost:8000/api/providers/{provider_id} \
  -H "Content-Type: application/json" \
  -d '{"api_key": "new-api-key"}'
```

#### Symptom: Rate limiting errors
**Solution**: Implement rate limiting or switch providers
```bash
# Check current rate limits
curl http://localhost:8000/api/providers/{provider_id}/limits

# Add a secondary provider as fallback
curl -X POST http://localhost:8000/api/providers \
  -H "Content-Type: application/json" \
  -d '{...}'
```

### Frontend Issues

#### Symptom: Frontend won't load
**Solution**: Check backend connection and restart frontend
```bash
# Check backend is running
curl http://localhost:8000/health

# Restart frontend
cd react
npm run dev
# or production
sudo systemctl restart vloop-harness-frontend
```

#### Symptom: Workspace windows not loading
**Solution**: Check iframe permissions and CORS settings
```bash
# Verify backend CORS configuration
curl -I http://localhost:8000/api/...

# Check browser console for CORS errors
```

## Backup and Recovery

### Database Backup (SQLite)

```bash
# Create backup
cp .harness/harness.db .harness/harness.db.backup.$(date +%Y%m%d)

# Automated backup script
#!/bin/bash
BACKUP_DIR="/backups/vloop"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
cp .harness/harness.db $BACKUP_DIR/harness.db.$DATE
# Keep last 7 days
find $BACKUP_DIR -name "harness.db.*" -mtime +7 -delete
```

### Database Backup (PostgreSQL)

```bash
# Create backup
pg_dump -h localhost -U vloop vloop > vloop_backup.sql

# Restore
psql -h localhost -U vloop vloop < vloop_backup.sql
```

### Component Backup

```bash
# Backup all components
tar -czf components_backup.tar.gz .harness/components/

# Restore
tar -xzf components_backup.tar.gz -C .harness/
```

### Disaster Recovery

1. **Stop all services**
   ```bash
   sudo systemctl stop vloop-harness
   sudo systemctl stop vloop-harness-frontend
   ```

2. **Restore database from backup**
   ```bash
   cp /backups/vloop/harness.db.20240123 .harness/harness.db
   ```

3. **Restore components**
   ```bash
   tar -xzf components_backup.tar.gz -C .harness/
   ```

4. **Restart services**
   ```bash
   sudo systemctl start vloop-harness
   sudo systemctl start vloop-harness-frontend
   ```

5. **Verify health**
   ```bash
   curl http://localhost:8000/health
   ```

## Performance Tuning

### Database Optimization

#### SQLite
```bash
# Enable WAL mode for better concurrency
sqlite3 .harness/harness.db "PRAGMA journal_mode=WAL;"

# Run VACUUM to reclaim space
sqlite3 .harness/harness.db "VACUUM;"

# Analyze query performance
sqlite3 .harness/harness.db "EXPLAIN QUERY PLAN SELECT * FROM agent_runs;"
```

#### PostgreSQL
```sql
-- Create indexes for common queries
CREATE INDEX idx_agent_runs_status ON agent_runs(status);
CREATE INDEX idx_agent_runs_created_at ON agent_runs(created_at);
CREATE INDEX idx_tool_traces_run_id ON tool_traces(run_id);

-- Update statistics
ANALYZE agent_runs;
ANALYZE tool_traces;
```

### Backend Optimization

#### Increase Worker Processes
```python
# In harness/main.py
uvicorn.run(
    "harness.server.app:app",
    host="0.0.0.0",
    port=8000,
    workers=4,  # Increase based on CPU cores
)
```

#### Enable Response Compression
```python
# In harness/server/app.py
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

### Frontend Optimization

#### Enable Code Splitting
```typescript
// In react/src/components/root/App.tsx
const ContextualPanel = lazy(() => import('./ContextualPanel'));
const WorkspaceArea = lazy(() => import('./WorkspaceArea'));
```

#### Configure Bundle Size Limits
```javascript
// In react/vite.config.ts
build: {
  rollupOptions: {
    output: {
      manualChunks: {
        vendor: ['react', 'react-dom'],
        mui: ['@mui/material', '@mui/icons-material'],
      },
    },
  },
}
```

### Resource Limits

#### Set Memory Limits (systemd)
```ini
# In /etc/systemd/system/vloop-harness.service
[Service]
MemoryLimit=2G
CPUQuota=200%
```

#### Set Disk Space Monitoring
```bash
# Add cron job to check disk space
0 * * * * df -h /path/to/vloop | awk '$5 > 80 { print "Disk usage high" }'
```

## Security Hardening

### API Key Management
- Store API keys in environment variables, not in code
- Rotate API keys regularly
- Use secret management service in production

### Network Security
- Use HTTPS in production
- Configure firewall to restrict access
- Enable rate limiting on API endpoints

### File System Security
- Set appropriate permissions on workspace directory
- Restrict file system tool to specific directories
- Enable audit logging for file operations

## Maintenance Schedule

### Daily
- Check system health endpoints
- Review error logs
- Monitor resource usage

### Weekly
- Review agent run success rates
- Check for failed component validations
- Backup database

### Monthly
- Review and rotate API keys
- Clean up old agent runs (> 90 days)
- Update dependencies
- Review security patches

### Quarterly
- Full system audit
- Performance benchmarking
- Disaster recovery drill
- Documentation update
