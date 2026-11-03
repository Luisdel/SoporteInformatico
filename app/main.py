from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import Settings, load_settings
from app.db import init_db, connect
from app.catalogs import seed_defaults
from app.pcinfo import collect
from app.security import RateLimiter
from app.routes import auth as routes_auth
from app.routes import public as routes_public


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Soporte Informático", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.templates = Jinja2Templates(directory="app/templates")
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

    app.include_router(routes_auth.router)
    app.include_router(routes_public.router)

    @app.get("/salud")
    def salud():
        return {"status": "ok"}

    return app


app = create_app()
