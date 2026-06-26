## 2024-06-26 - Control Plane HTTP Security Headers
**Vulnerability:** The Python Control Plane HTTP shell lacked Defense-in-Depth security headers (CSP, X-Frame-Options, X-Content-Type-Options, Strict-Transport-Security), exposing the interface to various web-based attacks (XSS, Clickjacking).
**Learning:** Since the HTTP shell uses `http.server.BaseHTTPRequestHandler` instead of FastAPI, security headers must be manually injected into all HTTP responses via a custom method rather than relying on middleware.
**Prevention:** Always implement an explicit header injection method (e.g., `_send_security_headers()`) for standard library HTTP servers and call it before `end_headers()` in all write methods (`_write_json`, `_write_html`, `_write_file`).
