## 2024-05-18 - Missing Defense-in-Depth Headers in Control Plane HTTP Server
**Vulnerability:** The Python Control Plane HTTP Server (`http_handler.py` / `http_responders.py`) was omitting security headers (like Content-Security-Policy, X-Frame-Options, X-Content-Type-Options) in its responses, leading to an increased risk of XSS, Clickjacking, and MIME-sniffing vulnerabilities.
**Learning:** Security headers are easily overlooked when using a low-level HTTP server (`http.server.BaseHTTPRequestHandler`) instead of a fully-featured framework like FastAPI, especially for serving static fallback shells.
**Prevention:** Always implement a dedicated function to inject baseline defense-in-depth security headers for all response types (JSON, HTML, files) in custom HTTP server implementations.
