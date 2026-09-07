import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import discovery

router = APIRouter()


class DiscoveryScanRequest(BaseModel):
    subnet: str
    force: bool = False


class PortScanRequest(BaseModel):
    host: str
    ports: str = ""
    force: bool = False


@router.post("/discovery/scan")
async def discovery_scan(payload: DiscoveryScanRequest):
    # Validated up front so a bad subnet still gets a normal response —
    # once the streaming response below starts, the 200 status is already sent.
    try:
        network = discovery.parse_ipv4_subnet(payload.subnet, force=payload.force)
    except discovery.ConfirmRequired as exc:
        raise HTTPException(status_code=409, detail={"confirm_required": True, "message": str(exc)})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    async def stream():
        async for event in discovery.sweep_subnet_stream(network):
            yield json.dumps(event) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/discovery/port-scan")
async def discovery_port_scan(payload: PortScanRequest):
    # Validated up front, same reasoning as the subnet sweep above.
    try:
        ip = discovery.resolve_scan_host(payload.host)
        ports = discovery.parse_ports(payload.ports, force=payload.force)
    except discovery.ConfirmRequired as exc:
        raise HTTPException(status_code=409, detail={"confirm_required": True, "message": str(exc)})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    async def stream():
        async for event in discovery.scan_ports_stream(ip, ports):
            yield json.dumps(event) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")
