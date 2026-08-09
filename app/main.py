"""FastAPI application factory.

Phase 1: skeleton with /health, request-id middleware, CORS, structured logging.
Later phases attach routers under api/routes.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_config
from app.core.logging import new_request_id, set_request_id, setup_logging
from app.db.base import configure_database, init_db


def create_app(auto_create_db: bool = True, db_url: str | None = None) -> FastAPI:
    cfg = get_config()
    setup_logging(
        level=cfg.env.log_level,
        fmt=cfg.settings.get("logging", {}).get("format", "json"),
        redact_fields=cfg.redact_fields,
    )
    app_settings = cfg.settings.get("app", {})

    if db_url:
        configure_database(db_url)

    if auto_create_db:
        init_db()

    app = FastAPI(
        title=cfg.app_name,
        version=app_settings.get("version", "0.1.0"),
        debug=cfg.is_debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.settings.get("server", {}).get("cors_origins", ["*"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        set_request_id(new_request_id())
        logger = logging.getLogger("app.access")
        start = time.monotonic()
        resp = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            resp.status_code,
            elapsed_ms,
            extra={"data": {"method": request.method, "path": request.url.path, "status": resp.status_code}},
        )
        return resp

    @app.get("/health")
    async def health() -> dict:
        return {
            "name": cfg.app_name,
            "version": app_settings.get("version", "0.1.0"),
            "status": "ok",
            "environment": cfg.env.environment,
        }

    register_app_routes(app)

    return app


def register_app_routes(app: FastAPI) -> None:
    """Attach API routers + static frontend."""
    from app.api.routes import auth, chat, conversations

    app.include_router(auth.router)
    app.include_router(conversations.router)
    app.include_router(chat.router)

    # TODO(phase5+): include documents.router

    from fastapi.staticfiles import StaticFiles
    from pathlib import Path

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


app = create_app()


if __name__ == "__main__":
    import uvicorn

    server = get_config().settings.get("server", {})
    uvicorn.run("app.main:app", host=server.get("host", "0.0.0.0"), port=server.get("port", 8000), reload=False)