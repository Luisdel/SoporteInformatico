from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import Settings, load_settings
from app.db import init_db
from app.security import RateLimiter
from app.routes import auth as routes_auth


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Soporte Informático", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.templates = Jinja2Templates(directory="app/templates")
    app.state.login_limiter = RateLimiter()
    app.state.public_limiter = RateLimiter()
    init_db(settings.db_path)

    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    app.include_router(routes_auth.router)

    @app.get("/salud")
    def salud():
        return {"status": "ok"}

    return app


app = create_app()