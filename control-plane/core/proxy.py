from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()

# We will inject the gateway instance dynamically when starting the proxy
gateway = None

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible endpoint that intercepts requests from sandboxed harnesses (like Aider),
    checks them against the global LLMGateway limits, and proxies them to the real LLM.
    """
    if gateway is None:
        raise HTTPException(status_code=500, detail="LLM Gateway not configured for Proxy")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    model = data.get("model", "gpt-4o-mini")
    messages = data.get("messages", [])

    # We enforce limits at the gateway layer
    try:
        response = gateway.generate(model=model, messages=messages, **{k: v for k, v in data.items() if k not in ["model", "messages"]})
    except Exception as e:
        if "Limit" in str(e):
            print(f"[KILL SWITCH ACTIVATED] Harness exceeded token limits: {e}")
            raise HTTPException(status_code=429, detail=f"VLoop Token Budget Exceeded: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Reconstruct the response to match OpenAI's schema
    return JSONResponse(content={
        "id": getattr(response, "id", "chatcmpl-mock"),
        "object": "chat.completion",
        "created": getattr(response, "created", 0),
        "model": getattr(response, "model", model),
        "choices": [
            {
                "index": i,
                "message": {
                    "role": "assistant",
                    "content": choice.message.content
                },
                "finish_reason": "stop"
            }
            for i, choice in enumerate(getattr(response, "choices", []))
        ],
        "usage": {
            "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) if hasattr(response, "usage") else 0,
            "completion_tokens": getattr(response.usage, "completion_tokens", 0) if hasattr(response, "usage") else 0,
            "total_tokens": getattr(response.usage, "total_tokens", 0) if hasattr(response, "usage") else 0,
        }
    })

def run_proxy(gw_instance, host="0.0.0.0", port=4000):
    global gateway
    gateway = gw_instance
    print(f"Starting Local LLM Proxy Trap on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
