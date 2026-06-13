## 2026-06-06 - [Fix permissive CORS configuration]
**Vulnerability:** Overly permissive CORS configuration (`allow_origins=["*"]`) allowed cross-origin requests from any domain, creating a security vulnerability for CSRF and data leakage.
**Learning:** Default FastAPI examples or quick setups often use wildcard CORS, which mistakenly gets deployed. FastApi allows setting string limits, but often applications use comma-separated env vars which requires manual splitting.
**Prevention:** Strictly define `ALLOWED_ORIGINS` dynamically through an environment variable and load it securely through pydantic settings, instead of using wildcards.

## 2026-06-13 - [Increase PBKDF2 iterations to meet OWASP recommendations]
**Vulnerability:** Weak password hashing parameters (100,000 iterations for PBKDF2-HMAC-SHA256) were used, making password hashes more vulnerable to brute-force and dictionary attacks.
**Learning:** Default or commonly copied parameters for PBKDF2 are often outdated and insufficient for modern computing speeds. The number of iterations must be periodically reviewed and increased.
**Prevention:** Use OWASP recommended iteration counts (at least 600,000 for PBKDF2-HMAC-SHA256 as of recent guidelines) and ensure the verification function securely parses the iteration count from the hash string instead of hardcoding it.
