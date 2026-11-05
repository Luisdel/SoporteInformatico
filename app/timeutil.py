from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def from_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def fmt_local(iso_ts: str | None, tz: str) -> str:
    if iso_ts is None:
        return "—"
    dt = from_iso(iso_ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(tz)).strftime("%d/%m/%Y %H:%M")


GFH_MONTHS = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)


def to_gfh(value: datetime | str | None) -> str:
    """Fecha y hora en formato GFH/DTG Zulú: DDHHMMZMMMYY."""
    if value is None or value == "":
        return "—"
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = from_iso(value)
        except (TypeError, ValueError):
            return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return (
        f"{dt.day:02d}{dt.hour:02d}{dt.minute:02d}"
        f"Z{GFH_MONTHS[dt.month - 1]}{dt.year % 100:02d}"
    )
