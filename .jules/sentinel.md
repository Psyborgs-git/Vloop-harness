## 2024-06-11 - SSRF Vulnerability in BrowserTool Prefix Matching
**Vulnerability:** The `BrowserTool`'s origin verification allowed SSRF bypasses because it used `url.startswith(prefix)` to check against allowed origins. An allowed prefix like `http://localhost` could be bypassed by a URL like `http://localhost.evil.com`.
**Learning:** Naive string prefix matching is inherently insecure for URL validation. It does not enforce domain or path boundaries correctly.
**Prevention:** Always use proper URL parsing utilities like `urllib.parse.urlparse` and independently validate the scheme, hostname, port, and path to ensure exact matches.
