from fastapi import FastAPI

from app.config import Settings, load_settings
from app.db import init_db


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Soporte Informático", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    init_db(settings.db_path)

    @app.get("/salud")
    def salud():
        return {"status": "ok"}

    return app


app = create_app()
