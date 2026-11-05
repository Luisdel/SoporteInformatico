from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import Settings, load_settings
from app.db import init_db, connect
from app.catalogs import seed_defaults
from app.pcinfo import collect
from app.security import RateLimiter
from app.routes import auth as routes_auth
from app.routes import public as routes_public
from app.routes import files as routes_files
from app.routes import admin as routes_admin
from app.routes import api as routes_api
from app.templating import templates


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Soporte Informático", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.templates = templates
    app.state.login_limiter = RateLimiter()
    app.state.public_limiter = RateLimiter()
    app.state.pcinfo_collector = collect
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        seed_defaults(conn)
    finally:
        conn.close()

    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    app.include_router(routes_public.router)
    app.include_router(routes_auth.router)
    app.include_router(routes_files.router)
    app.include_router(routes_admin.router)
    app.include_router(routes_api.router)

    @app.get("/salud")
    @app.get("/health")
    def salud():
        return {"status": "ok"}

    return app


app = create_app()
