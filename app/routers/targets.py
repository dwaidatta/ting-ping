from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator, model_validator

from app.config import settings
from app.models import CheckMethod, Target
from app.storage import save_targets

router = APIRouter()


class ReorderRequest(BaseModel):
    order: list[str]


class TargetRequest(BaseModel):
    name: str = ""
    host: str
    method: CheckMethod
    interval_s: int
    enabled: bool = True
    tcp_port: Optional[int] = None
    http_path: Optional[str] = None
    http_scheme: Optional[str] = None

    @model_validator(mode="after")
    def _default_name_to_host(self) -> "TargetRequest":
        """An unnamed monitor is labelled by whatever it points at."""
        self.host = self.host.strip()
        if not self.host:
            raise ValueError("host is required")
        self.name = self.name.strip() or self.host
        return self

    @field_validator("interval_s")
    @classmethod
    def _validate_interval(cls, v: int) -> int:
        if not (settings.interval_min_s <= v <= settings.interval_max_s):
            raise ValueError(
                f"interval_s must be between {settings.interval_min_s} and {settings.interval_max_s}"
            )
        return v

    def validate_method_fields(self) -> None:
        if self.method == CheckMethod.TCP and not self.tcp_port:
            raise HTTPException(status_code=422, detail="tcp_port is required for method=tcp")


def _all_targets(request: Request) -> list[Target]:
    return request.app.state.scheduler.targets()


@router.get("/targets")
async def list_targets(request: Request):
    return [t.to_json() for t in _all_targets(request)]


@router.post("/targets", status_code=201)
async def create_target(payload: TargetRequest, request: Request):
    payload.validate_method_fields()
    scheduler = request.app.state.scheduler

    target = Target.new(
        position=len(scheduler.targets()),  # new monitors land at the end of the grid
        name=payload.name,
        host=payload.host,
        method=payload.method.value,
        interval_s=payload.interval_s,
        enabled=payload.enabled,
        tcp_port=payload.tcp_port,
        http_path=payload.http_path,
        http_scheme=payload.http_scheme,
    )

    scheduler.add(target)
    save_targets(scheduler.targets())
    await request.app.state.ws_manager.broadcast({"type": "target_added", "target": target.to_json()})
    return target.to_json()


@router.put("/targets/order")
async def reorder_targets(payload: ReorderRequest, request: Request):
    """Persist the grid order produced by dragging a card.

    Takes the full list of target ids in their new order. Unknown ids are
    ignored and omitted ones keep their relative order at the end, so a stale
    list from a client that missed an add or delete still reorders sanely
    instead of failing.
    """
    scheduler = request.app.state.scheduler

    scheduler.reorder(payload.order)
    ordered = scheduler.targets()
    save_targets(ordered)

    order = [t.id for t in ordered]
    await request.app.state.ws_manager.broadcast({"type": "targets_reordered", "order": order})
    return {"order": order}


@router.put("/targets/{target_id}")
async def update_target(target_id: str, payload: TargetRequest, request: Request):
    payload.validate_method_fields()
    scheduler = request.app.state.scheduler

    existing = next((t for t in scheduler.targets() if t.id == target_id), None)
    if existing is None:
        raise HTTPException(status_code=404, detail="target not found")

    target = Target(
        id=target_id,
        position=existing.position,  # editing a monitor leaves it where it sits
        name=payload.name,
        host=payload.host,
        method=payload.method,
        interval_s=payload.interval_s,
        enabled=payload.enabled,
        tcp_port=payload.tcp_port,
        http_path=payload.http_path,
        http_scheme=payload.http_scheme,
    )

    scheduler.update(target)
    save_targets(scheduler.targets())
    await request.app.state.ws_manager.broadcast({"type": "target_updated", "target": target.to_json()})
    return target.to_json()


@router.delete("/targets/{target_id}", status_code=204)
async def delete_target(target_id: str, request: Request):
    scheduler = request.app.state.scheduler

    if target_id not in {t.id for t in scheduler.targets()}:
        raise HTTPException(status_code=404, detail="target not found")

    scheduler.remove(target_id)
    save_targets(scheduler.targets())
    await request.app.state.ws_manager.broadcast({"type": "target_removed", "target_id": target_id})
