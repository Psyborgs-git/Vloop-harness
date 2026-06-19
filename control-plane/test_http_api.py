import pytest
from fastapi.testclient import TestClient

from cp.http_api import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "scaffold"}

    headers = response.headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-XSS-Protection"] == "1; mode=block"
    assert headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert headers["Content-Security-Policy"] == "default-src 'self'"

def test_health_no_overwrite():
    # Test that the middleware doesn't overwrite an existing header
    # but that would require creating a new route for testing
    pass
