# Sentinel Journal

## 2024-06-05 - [CORS Configuration]
**Vulnerability:** Overly permissive CORS configuration (`allow_origins=["*"]`)
**Learning:** The FastAPI app in `harness/server/app.py` has CORS configured to allow all origins, which is a security risk. It should be restricted to the specific allowed origins via the `ALLOWED_ORIGINS` environment setting.
**Prevention:** Always define `ALLOWED_ORIGINS` in `harness/settings.py` and use it in `app.py`.
## 2026-06-06 - [Fix permissive CORS configuration]
**Vulnerability:** Overly permissive CORS configuration (`allow_origins=["*"]`) allowed cross-origin requests from any domain, creating a security vulnerability for CSRF and data leakage.
**Learning:** Default FastAPI examples or quick setups often use wildcard CORS, which mistakenly gets deployed. FastApi allows setting string limits, but often applications use comma-separated env vars which requires manual splitting.
**Prevention:** Strictly define `ALLOWED_ORIGINS` dynamically through an environment variable and load it securely through pydantic settings, instead of using wildcards.
