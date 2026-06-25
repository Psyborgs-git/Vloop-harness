## 2026-06-25 - Missing security headers for API responses
**Vulnerability:** Control-plane HTTP responses lacked basic Defense-in-Depth security headers (CSP, HSTS, X-Frame-Options, XSS-Protection).
**Learning:** Python-based HTTP services need these injected explicitly in their request handlers.
**Prevention:** Implement `_send_security_headers()` for any base `BaseHTTPRequestHandler` responses.
