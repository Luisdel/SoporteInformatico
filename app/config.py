from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Settings:
    host: str
    port: int
    db_path: Path
    upload_dir: Path
    timezone: str
    trusted_proxies: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]
    tls_cert: Path | None
    tls_key: Path | None
    session_hours: int
    max_upload_mb: int
    secure_cookies: bool
    pbkdf2_iterations: int
    resolve_hostnames: bool


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _as_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_path(value: str | None) -> Path | None:
    return Path(value) if value else None


def load_settings(env: dict[str, str] | None = None) -> Settings:
    if env is None:
        load_dotenv()
        env = os.environ

    def get(key: str, default: str) -> str:
        return env.get(key) or default

    proxies = tuple(
        ipaddress.ip_network(item.strip())
        for item in get("TRUSTED_PROXIES", "").split(",")
        if item.strip()
    )

    return Settings(
        host=get("APP_HOST", "0.0.0.0"),
        port=_as_int(get("APP_PORT", "8000"), 8000),
        db_path=Path(get("DB_PATH", "data/incidencias.db")),
        upload_dir=Path(get("UPLOAD_DIR", "data/uploads")),
        timezone=get("TIMEZONE", "Europe/Madrid"),
        trusted_proxies=proxies,
        tls_cert=_as_path(get("TLS_CERT", "")),
        tls_key=_as_path(get("TLS_KEY", "")),
        session_hours=_as_int(get("SESSION_HOURS", "12"), 12),
        max_upload_mb=_as_int(get("MAX_UPLOAD_MB", "5"), 5),
        secure_cookies=_as_bool(get("SECURE_COOKIES", "0")),
        pbkdf2_iterations=_as_int(get("PBKDF2_ITERATIONS", "600000"), 600_000),
        resolve_hostnames=_as_bool(get("RESOLVE_HOSTNAMES", "1")),
    )
