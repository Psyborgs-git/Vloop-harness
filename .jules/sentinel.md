## 2026-06-06 - [Fix permissive CORS configuration]
**Vulnerability:** Overly permissive CORS configuration (`allow_origins=["*"]`) allowed cross-origin requests from any domain, creating a security vulnerability for CSRF and data leakage.
**Learning:** Default FastAPI examples or quick setups often use wildcard CORS, which mistakenly gets deployed. FastApi allows setting string limits, but often applications use comma-separated env vars which requires manual splitting.
**Prevention:** Strictly define `ALLOWED_ORIGINS` dynamically through an environment variable and load it securely through pydantic settings, instead of using wildcards.
## 2026-06-12 - [Fix unauthenticated admin registration endpoint]
**Vulnerability:** The `/register` endpoint was unauthenticated, allowing any user to create new user accounts (which function as admin in this application), due to missing `require_admin` dependency.
**Learning:** In initial application setup, it's common to leave administrative creation endpoints open for convenience, but they must be closed or placed behind proper setup guards to prevent takeover in production.
**Prevention:** Ensure that admin registration endpoints correctly utilize `current_user: User = Depends(require_admin)` or require an invite code for initialization.
