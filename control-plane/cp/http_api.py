"""CP HTTP/WebSocket API scaffold."""

from fastapi import FastAPI

app = FastAPI(title="VLoop Control Plane")


@app.get("/health")
def health() -> dict:
    return {"status": "scaffold"}
