
## 2024-05-18 - [Defense-in-Depth] HTTP Responders Missing Security Headers
**Vulnerability:** The HTTP responders in `control-plane/cp/http_responders.py` were missing standard Defense-in-Depth security headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection). This increases the attack surface for vulnerabilities like XSS, Clickjacking, and MIME-sniffing.
**Learning:** Due to the custom `http.server.BaseHTTPRequestHandler` implementation used by the control-plane fallback HTTP shell, standard middleware-based header injection wasn't present. The Vite React frontend requires specific CSP directives (`unsafe-inline`, `ws:`, `wss:`) for hot-reloading and dynamic script evaluation.
**Prevention:** Always ensure that custom HTTP server implementations explicitly set Defense-in-Depth security headers on all responses, tailored to the specific needs of the frontend architecture.
