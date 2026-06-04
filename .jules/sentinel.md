## 2024-06-04 - Overly Permissive CORS Configuration
**Vulnerability:** Found `allow_origins=["*"]` configured in the backend's `CORSMiddleware`.
**Learning:** This is a classic misconfiguration that exposes the API to unauthorized cross-origin requests, potentially leading to CSRF vulnerabilities, especially if the API relies on cookies or other implicit authentication.
**Prevention:** Always use a specific allowlist of trusted origins for `allow_origins`, especially when configuring APIs that manage sensitive actions. Added `ALLOWED_ORIGINS` to `HarnessSettings` and updated `CORSMiddleware` accordingly.
