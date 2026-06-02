from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Diagnosis Agent API",
        version="0.1.0",
        description="HTTP API for the LangGraph-based diagnosis agent.",
    )
    app.include_router(api_router, prefix="/api/v1")
    web_dir = Path(__file__).resolve().parent / "web"
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


app = create_app()
