from app.timeutil import fmt_local

def test_fmt_local_usa_madrid():
    assert fmt_local("2026-11-03T08:12:00+00:00", "Europe/Madrid") == "03/11/2026 09:12"

def test_fmt_local_none():
    assert fmt_local(None, "Europe/Madrid") == "—"
