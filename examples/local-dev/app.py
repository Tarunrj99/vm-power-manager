"""Local development server — FastAPI wrapper for testing without deploying."""

import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from vm_power_manager import check_idle, handle_slack  # noqa: E402

app = FastAPI(title="VM Power Manager — Local Dev")
CONFIG = os.environ.get("VM_POWER_MANAGER_CONFIG", str(Path(__file__).parent / "config.yaml"))


@app.post("/monitor")
async def monitor_endpoint():
    """Simulate Cloud Scheduler trigger."""
    result = check_idle(config=CONFIG)
    return JSONResponse(content=result)


@app.post("/slack")
async def slack_endpoint(request: Request):
    """Slack commands and interactions endpoint."""
    result = handle_slack(request, config=CONFIG)
    if isinstance(result, tuple):
        return JSONResponse(content=result[0], status_code=result[1])
    return JSONResponse(content=result)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "vm-power-manager-dev"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
