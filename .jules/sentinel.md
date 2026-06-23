## 2024-05-18 - Missing Defense-in-Depth Headers in Raw HTTP Shell
**Vulnerability:** The HTTP shell powered by `http.server.BaseHTTPRequestHandler` was responding to frontend and API requests without basic security headers, missing protections against XSS, clickjacking, MIME-sniffing, and lacking HSTS and CSP constraints.
**Learning:** Raw HTTP frameworks in standard libraries (unlike modern web frameworks like FastAPI) do not include basic defense-in-depth headers by default, requiring explicit injection for all response types.
**Prevention:** Ensure explicit wrapper/middleware methods exist to globally apply security headers when rolling custom HTTP servers or interacting directly with low-level server handlers.
