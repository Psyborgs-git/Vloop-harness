import time

from fastapi import APIRouter

router = APIRouter()
_start = time.time()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "uptime_s": round(time.time() - _start, 2),
    }
