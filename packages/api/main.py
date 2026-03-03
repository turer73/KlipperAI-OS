"""FastAPI application factory."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    # TODO: DB init, MoonrakerClient init
    yield
    # TODO: cleanup

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
    from .routers import printer as printer_router
    app.include_router(printer_router.router)
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
