## 2026-06-27 - Add missing defense-in-depth security headers
**Vulnerability:** The HTTP shell uses `http.server.BaseHTTPRequestHandler` which does not inject typical framework-provided security headers (e.g., CSP, X-Frame-Options) by default.
**Learning:** When using low-level handlers like `BaseHTTPRequestHandler`, defense-in-depth security headers must be manually injected into all HTTP responses.
**Prevention:** Always ensure a centralized method injects headers like `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Strict-Transport-Security`, and `Content-Security-Policy` when building custom HTTP handlers.
