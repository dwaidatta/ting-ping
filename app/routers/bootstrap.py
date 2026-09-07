from fastapi import APIRouter, Request

from app.checks.status import status_catalog
from app.config import settings

router = APIRouter()


@router.get("/state")
async def get_state(request: Request):
    scheduler = request.app.state.scheduler
    return {
        "targets": scheduler.snapshot(),
        "limits": {
            "interval_min_s": settings.interval_min_s,
            "interval_max_s": settings.interval_max_s,
            "default_interval_s": settings.default_interval_s,
            "buffer_size": settings.buffer_size,
        },
        "status_codes": status_catalog(),
    }
