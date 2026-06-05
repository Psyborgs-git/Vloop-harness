# Sentinel Journal

## 2024-06-05 - [CORS Configuration]
**Vulnerability:** Overly permissive CORS configuration (`allow_origins=["*"]`)
**Learning:** The FastAPI app in `harness/server/app.py` has CORS configured to allow all origins, which is a security risk. It should be restricted to the specific allowed origins via the `ALLOWED_ORIGINS` environment setting.
**Prevention:** Always define `ALLOWED_ORIGINS` in `harness/settings.py` and use it in `app.py`.
