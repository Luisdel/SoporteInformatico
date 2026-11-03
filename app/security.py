from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Callable

from app.timeutil import utcnow, to_iso

HASH_ALGORITHM = "pbkdf2_sha256"
SALT_BYTES = 16
MIN_ITERATIONS = 1
MAX_ITERATIONS = 2_000_000
SESSION_DAYS = 7
PURGE_MIN_KEYS = 1024
PURGE_INTERVAL_SECONDS = 60.0


def hash_password(password: str, iterations: int = 600_000) -> str:
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        (
            HASH_ALGORITHM,
            str(iterations),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, hash_text = encoded.split("$")
        if algorithm != HASH_ALGORITHM:
            return False
        iterations = int(iterations_text)
        if not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
            return False
        salt = base64.b64decode(salt_text, validate=True)
        expected = base64.b64decode(hash_text, validate=True)
    except (ValueError, TypeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected)


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_admin_session(
    conn,
    admin_id: int,
    *,
    ip: str | None,
    user_agent: str | None,
    hours: int,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Crea una sesión de admin y devuelve `(token, csrf)`.

    `hours` se mantiene por compatibilidad con la firma del plan, pero no
    altera la expiración: la sesión caduca siempre de forma absoluta a los 7
    días. La caducidad por inactividad se aplica al buscarla con
    `find_admin_session(..., idle_hours=...)`.
    """
    current = now or utcnow()
    token = new_token()
    csrf = new_token()
    conn.execute(
        """
        insert into admin_sessions(
            token_hash, csrf_token, admin_id, created_at, last_seen_at,
            expires_at, ip, user_agent
        ) values(?,?,?,?,?,?,?,?)
        """,
        (
            hash_token(token),
            csrf,
            admin_id,
            to_iso(current),
            to_iso(current),
            to_iso(current + timedelta(days=SESSION_DAYS)),
            ip,
            user_agent,
        ),
    )
    return token, csrf


def find_admin_session(
    conn,
    token: str,
    *,
    now: datetime | None = None,
    idle_hours: int = 12,
):
    current = now or utcnow()
    idle_limit = current - timedelta(hours=idle_hours)
    return conn.execute(
        """
        select s.id as session_id, s.csrf_token,
               a.id as admin_id, a.username, a.display_name, a.role
          from admin_sessions s
          join admins a on a.id = s.admin_id
         where s.token_hash = ?
           and a.active = 1
           and s.expires_at > ?
           and s.last_seen_at > ?
        """,
        (hash_token(token), to_iso(current), to_iso(idle_limit)),
    ).fetchone()


def touch_admin_session(
    conn, session_id: int, *, now: datetime | None = None
) -> None:
    conn.execute(
        "update admin_sessions set last_seen_at = ? where id = ?",
        (to_iso(now or utcnow()), session_id),
    )


def delete_admin_session(conn, token: str) -> None:
    conn.execute(
        "delete from admin_sessions where token_hash = ?", (hash_token(token),)
    )


class RateLimiter:
    """Límite de intentos por clave con ventana deslizante.

    Las claves cuyas marcas han salido de su ventana se purgan para que el
    diccionario no crezca sin cota con claves controladas por el cliente. Con
    pocas claves la purga es inmediata; con muchas se amortiza a un barrido
    cada `PURGE_INTERVAL_SECONDS` para no convertir el propio limitador en un
    coste de CPU.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._windows: dict[str, float] = {}
        self._last_purge = self._clock()

    def hit(self, key: str, limit: int, window: float) -> bool:
        now = self._clock()
        self._purge_if_needed(now)
        marks = self._hits.setdefault(key, deque())
        self._windows[key] = window
        cutoff = now - window
        while marks and marks[0] <= cutoff:
            marks.popleft()
        if len(marks) >= limit:
            return False
        marks.append(now)
        return True

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)
        self._windows.pop(key, None)

    def _purge_if_needed(self, now: float) -> None:
        if (
            len(self._hits) >= PURGE_MIN_KEYS
            and now - self._last_purge < PURGE_INTERVAL_SECONDS
        ):
            return
        self._last_purge = now
        stale = [
            key
            for key, marks in self._hits.items()
            if not marks
            or marks[-1] <= now - self._windows.get(key, 0.0)
        ]
        for key in stale:
            del self._hits[key]
            self._windows.pop(key, None)
