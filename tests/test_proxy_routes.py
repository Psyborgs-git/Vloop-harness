from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from harness.server.routes import proxy


class _FakeViteResponse:
    def __init__(self, text: str = "<html><head></head><body>ok</body></html>", status_code: int = 200) -> None:
        self.text = text
        self.content = text.encode()
        self.status_code = status_code
        self.headers = {"content-type": "text/html"}


class _FakeAsyncClient:
    def __init__(self, responses: list[_FakeViteResponse] | None = None, exc: Exception | None = None):
        self._responses = responses or [_FakeViteResponse()]
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, *_args, **_kwargs):
        if self._exc is not None:
            raise self._exc
        return self._responses.pop(0)


@pytest.fixture
def proxy_app() -> FastAPI:
    app = FastAPI()
    app.include_router(proxy.router)
    app.state.main_process = MagicMock()
    app.state.settings = SimpleNamespace(
        harness_host="127.0.0.1",
        harness_port=8000,
        vite_host="127.0.0.1",
        vite_port=5173,
        harness_debug=True,
        react_dist_dir="",
    )
    return app


@pytest.mark.asyncio
async def test_ui_root_debug_mode_proxies_vite_index(proxy_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proxy.httpx, "AsyncClient", lambda: _FakeAsyncClient())

    async with AsyncClient(transport=ASGITransport(app=proxy_app), base_url="http://test") as client:
        resp = await client.get("/ui/root")

    assert resp.status_code == 200
    assert "window.__HARNESS__" in resp.text
    assert '"API_URL": "http://127.0.0.1:8000/api/root"' in resp.text


@pytest.mark.asyncio
async def test_ui_root_debug_mode_missing_vite_returns_503(proxy_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        proxy.httpx,
        "AsyncClient",
        lambda: _FakeAsyncClient(exc=httpx.ConnectError("boom", request=httpx.Request("GET", "http://vite"))),
    )

    async with AsyncClient(transport=ASGITransport(app=proxy_app), base_url="http://test") as client:
        resp = await client.get("/ui/root")

    assert resp.status_code == 503
    assert "unreachable" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_ui_root_static_mode_serves_react_dist(proxy_app: FastAPI, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    dist = tmp_path / "react" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html><head></head><body>static</body></html>", encoding="utf-8")

    proxy_app.state.settings.harness_debug = False
    proxy_app.state.settings.react_dist_dir = str(dist)

    # Ensure static mode does not rely on Vite.
    monkeypatch.setattr(proxy.httpx, "AsyncClient", lambda: _FakeAsyncClient(exc=AssertionError("vite should not be called")))

    async with AsyncClient(transport=ASGITransport(app=proxy_app), base_url="http://test") as client:
        resp = await client.get("/ui/root")

    assert resp.status_code == 200
    assert "window.__HARNESS__" in resp.text
    assert "static" in resp.text


@pytest.mark.asyncio
async def test_ui_root_static_mode_missing_dist_returns_503(proxy_app: FastAPI) -> None:
    proxy_app.state.settings.harness_debug = False
    proxy_app.state.settings.react_dist_dir = "/definitely/missing/react/dist"

    async with AsyncClient(transport=ASGITransport(app=proxy_app), base_url="http://test") as client:
        resp = await client.get("/ui/root")

    assert resp.status_code == 503
    assert "dist directory" in resp.json()["detail"].lower()
