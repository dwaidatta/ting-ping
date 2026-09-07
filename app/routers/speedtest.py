import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import speedtest

router = APIRouter()


class SpeedtestRequest(BaseModel):
    provider: str = speedtest.DEFAULT_PROVIDER


@router.post("/speedtest/run")
async def speedtest_run(payload: SpeedtestRequest):
    if payload.provider not in speedtest.PROVIDERS:
        raise HTTPException(status_code=400, detail=f"provider must be one of {', '.join(speedtest.PROVIDERS)}")

    async def stream():
        async for event in speedtest.speedtest_stream(payload.provider):
            yield json.dumps(event) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")
