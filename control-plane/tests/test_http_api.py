from fastapi.testclient import TestClient
from cp.http_api import app

client = TestClient(app)

def test_health_endpoint_and_security_headers():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "scaffold"}

    # Check security headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert response.headers["Content-Security-Policy"] == "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com"
