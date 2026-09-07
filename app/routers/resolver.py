from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.resolver import resolve_query

router = APIRouter()


class ResolveRequest(BaseModel):
    query: str


@router.post("/resolve")
async def resolve(payload: ResolveRequest):
    try:
        return await resolve_query(payload.query)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
