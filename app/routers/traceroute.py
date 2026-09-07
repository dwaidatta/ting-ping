import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import traceroute
from app.config import settings

router = APIRouter()


class TracerouteRequest(BaseModel):
    host: str
    family: str = "auto"
    max_hops: int | None = None


@router.post("/traceroute/run")
async def traceroute_run(payload: TracerouteRequest):
    # Validated up front so a bad host or a missing binary still gets a normal
    # response — once the streaming response below starts, the 200 status is
    # already sent (same reasoning as the discovery scan endpoints).
    if traceroute.binary_missing():
        raise HTTPException(status_code=400, detail=f"'{traceroute.binary_name()}' is not available on this machine")

    if payload.family not in ("auto", "ipv4", "ipv6"):
        raise HTTPException(status_code=400, detail="family must be 'auto', 'ipv4' or 'ipv6'")

    try:
        target_ip, version = traceroute.resolve_target(payload.host, payload.family)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    max_hops = payload.max_hops or settings.traceroute_default_max_hops
    max_hops = max(1, min(max_hops, settings.traceroute_hard_max_hops))

    async def stream():
        async for event in traceroute.traceroute_stream(
            target_ip, version, max_hops, settings.traceroute_hop_timeout_s
        ):
            yield json.dumps(event) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")
