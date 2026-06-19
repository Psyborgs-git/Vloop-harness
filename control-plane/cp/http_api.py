"""CP HTTP/WebSocket API scaffold."""

from fastapi import FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send

app = FastAPI(title="VLoop Control Plane")


class SecurityHeadersMiddleware:
    """ASGI middleware to inject security headers into HTTP and WebSocket responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start" or message["type"] == "websocket.accept":
                headers = message.setdefault("headers", [])

                # Convert existing headers to a set of lowercased keys for quick lookup
                existing_headers = {k.decode("latin1").lower() for k, v in headers}

                security_headers = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
                    (b"content-security-policy", b"default-src 'self'"),
                ]

                for key, value in security_headers:
                    if key.decode("latin1") not in existing_headers:
                        headers.append((key, value))

            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(SecurityHeadersMiddleware)


@app.get("/health")
def health() -> dict:
    return {"status": "scaffold"}
