# Local Development Setup

## System Requirements
| Requirement | Minimum Version | How to Check | How to Install |
|---|---|---|---|
| Git | Any modern version | `git --version` | https://git-scm.com/downloads |
| Python | 3.11+ | `python --version` | https://www.python.org/downloads/ |
| pip | Bundled with Python | `pip --version` | `python -m ensurepip --upgrade` |
| Node.js | 18.18.0+ | `node --version` | https://nodejs.org/ |
| npm | Bundled with Node | `npm --version` | Comes with Node.js install |
| Playwright browsers (optional e2e) | matching @playwright/test | `ls /opt/pw-browsers` | `npx playwright install` (if not pre-provisioned) |

OS: Linux/macOS/Windows supported in principle; primary local workflow appears Linux/macOS oriented (`bash` examples).

## Step-by-Step Setup
### 1. Clone the repository
```bash
git clone <repo-url>
cd Vloop-harness
```

### 2. Install dependencies
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

cd react
npm install
cd ..
```

### 3. Configure environment
```bash
cp .env.example .env
```
Set/verify these values in `.env`:
- Required for all local runs: `HARNESS_HOST`, `HARNESS_PORT`, `HARNESS_DEBUG`, `VITE_HOST`, `VITE_PORT`.
- Required for hosted LLM providers: `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY`.
- Optional for local LLM: `OLLAMA_BASE_URL` (defaults to `http://localhost:11434`).
- Optional DB override: `VLOOP_DB_URL` for PostgreSQL.

### 4. Database setup
Default (SQLite): no manual migration command required; tables auto-create at startup.

Optional PostgreSQL:
```bash
export VLOOP_DB_URL='postgresql+asyncpg://user:password@localhost/vloop'
python -m harness.main services start backend
```

### 5. Start the application
```bash
python -m harness.main services start all
```
Open: `http://localhost:8000/ui/root`.
Success looks like: root dashboard loads and backend status endpoint (`GET /`) returns JSON `{"status":"ok",...}`.

### 6. Verify with tests
```bash
pytest
cd react && npm run typecheck && cd ..
```
Optional E2E:
```bash
cd react && npm run test:e2e && cd ..
```

## Common Issues & Fixes
| Problem | Symptom | Fix |
|---|---|---|
| Backend port in use | `Backend port conflict` error | Change `HARNESS_PORT` or stop conflicting process |
| Frontend port in use | Vite startup fails on 5173 | Change `VITE_PORT` or free port |
| Missing frontend deps | `node_modules` missing error from service manager | Run `cd react && npm install` |
| AI engine unavailable | Chat/view generation returns not configured | Create provider in Settings and set default |
| Invalid provider key | `/api/providers/{id}/test` returns error | Re-enter API key and model/base URL |
| Static mode assets missing | `react/dist` missing 503 | Run `cd react && npm run build` or use debug mode |
| Policy denial on tools | tool call fails with policy violation | Update project policy via `/api/tools/policy` if appropriate |
| Confirmation required | tool endpoint returns `202` | Confirm using `/api/tools/confirm/{token}` |
| SQLite file permissions | DB init/write errors in `.vloop` | Ensure workspace is writable |
| Python version mismatch | install/type errors | Use Python 3.11+ virtualenv |

## IDE Setup
- Python: enable Ruff + mypy + pytest integration.
- TypeScript/React: enable TypeScript language service; ESLint is not configured in this repository, so rely on TypeScript strict mode and code review.
- Recommended editor settings:
  - format on save
  - 100-char max line length for Python (matches Ruff config)
  - strict TS error visibility

## Working with Docker
No Dockerfile/compose configuration is currently committed; local development runs directly with Python + npm processes.

## Useful Dev Commands
```bash
# Start all services
python -m harness.main services start all

# Service status
python -m harness.main services status

# Stop all services
python -m harness.main services stop all

# Headless run mode
python -m harness.main run --no-window

# Static frontend serving mode
python -m harness.main run --frontend-mode static

# Python tests
pytest

# Frontend dev server manually
cd react && npm run dev
```

## Data Management
- Reset local harness/vloop runtime data:
```bash
rm -rf .harness .vloop
```
- Recreate DB state: restart backend after deletion.
- Seed data: default provider seeds are handled automatically in startup provider manager; no dedicated custom seed script exists in this repository.
- Migrations: explicit migration framework is not configured (`Base.metadata.create_all` is used).
