from fastapi import APIRouter, Request

from app.device_status import compute_device_status

router = APIRouter()


@router.get("/device-status")
async def get_device_status():
    """Read-only snapshot used by the UI on page load.

    Does not broadcast: only the client that asked needs it.
    """
    return await compute_device_status()


@router.post("/device-status")
async def device_status(request: Request):
    data = await compute_device_status()
    await request.app.state.ws_manager.broadcast({"type": "device_status", "data": data})
    return data
