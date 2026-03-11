"""FastAPI application factory."""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    from .db.engine import Database
    db = Database(settings.db_path)
    db.connect()
    app.state.db = db
    yield
    db.close()

def create_app() -> FastAPI:
    app = FastAPI(
        title="KlipperOS-AI API",
        version="3.0.0",
        description="KlipperOS-AI REST + WebSocket API",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from .routers import auth as auth_router
    from .routers import printer as printer_router
    from .routers import control as control_router
    from .routers import files as files_router
    from .routers import system as system_router
    from .routers import flowguard as flowguard_router
    from .routers import ws as ws_router
    from .routers import resources as resources_router
    from .routers import maintenance as maintenance_router
    from .routers import recovery as recovery_router
    from .routers import calibration as calibration_router
    from .routers import notifications as notifications_router
    from .routers import bambu as bambu_router
    app.include_router(auth_router.router)
    app.include_router(printer_router.router)
    app.include_router(control_router.router)
    app.include_router(files_router.router)
    app.include_router(system_router.router)
    app.include_router(flowguard_router.router)
    app.include_router(ws_router.router)
    app.include_router(resources_router.router)
    app.include_router(maintenance_router.router)
    app.include_router(recovery_router.router)
    app.include_router(calibration_router.router)
    app.include_router(notifications_router.router)
    app.include_router(bambu_router.router)
    return app

app = create_app()

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "version": "3.0.0"}

def main():
    import uvicorn
    uvicorn.run(
        "packages.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )

if __name__ == "__main__":
    main()
