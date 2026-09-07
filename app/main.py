import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import storage
from app.checks import http as http_checks
from app.config import settings
from app.routers import bootstrap, device, targets, ws
from app.scheduler import TargetScheduler
from app.ws_manager import ConnectionManager

logging.basicConfig(level=settings.log_level.upper())


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.targets_file.parent.mkdir(parents=True, exist_ok=True)
    http_checks.init_client()

    app.state.ws_manager = ConnectionManager()
    app.state.scheduler = TargetScheduler(broadcast_fn=app.state.ws_manager.broadcast)
    app.state.scheduler.load_initial(storage.load_targets())

    yield

    await app.state.scheduler.shutdown()
    await http_checks.close_client()


def create_app() -> FastAPI:
    app = FastAPI(title="TingPing", lifespan=lifespan)

    app.include_router(bootstrap.router, prefix="/api")
    app.include_router(targets.router, prefix="/api")
    app.include_router(device.router, prefix="/api")
    app.include_router(ws.router)

    app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(settings.static_dir / "index.html")

    return app


app = create_app()
