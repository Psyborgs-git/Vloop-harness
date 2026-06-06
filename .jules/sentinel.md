## 2026-06-06 - [Fix permissive CORS configuration]
**Vulnerability:** Overly permissive CORS configuration (`allow_origins=["*"]`) allowed cross-origin requests from any domain, creating a security vulnerability for CSRF and data leakage.
**Learning:** Default FastAPI examples or quick setups often use wildcard CORS, which mistakenly gets deployed. FastApi allows setting string limits, but often applications use comma-separated env vars which requires manual splitting.
**Prevention:** Strictly define `ALLOWED_ORIGINS` dynamically through an environment variable and load it securely through pydantic settings, instead of using wildcards.
