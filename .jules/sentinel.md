## 2024-05-20 - Add Security Headers to FastAPI
**Vulnerability:** Missing Security Headers
**Learning:** FastAPI does not include security headers by default. This leaves the API vulnerable to Clickjacking, XSS, and MIME-sniffing.
**Prevention:** Add a middleware to automatically inject X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Strict-Transport-Security, and Content-Security-Policy headers.
