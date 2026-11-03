import subprocess
from datetime import datetime
from ipaddress import ip_network

from app.pcinfo import ClientInfo, client_ip, lookup_mac, lookup_hostname, parse_user_agent, collect, default_gateway_mac


def fake_request(peer, headers=None):
    from starlette.requests import Request
    raw = [(b"host", b"test")] + [(k.encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http", "method": "GET", "path": "/",
        "headers": raw, "client": (peer, 1234),
        "query_string": b"", "scheme": "http", "server": ("t", 80)
    }
    return Request(scope)


def test_xff_solo_desde_proxy_confiable():
    req = fake_request("10.0.0.5", {"x-forwarded-for": "1.2.3.4, 10.0.0.5"})
    assert client_ip(req, (ip_network("10.0.0.0/8"),)) == "1.2.3.4"
    assert client_ip(req, ()) == "10.0.0.5"


def test_mac_linux_y_windows():
    out_linux = "192.168.1.20 dev eth0 lladdr 3c:7c:3f:1a:2b:9d REACHABLE\n"
    run_linux = lambda cmd: subprocess.CompletedProcess(cmd, 0, out_linux, "")
    assert lookup_mac("192.168.1.20", runner=run_linux, system="Linux") == "3C:7C:3F:1A:2B:9D"
    out_windows = "  192.168.1.20          3c-7c-3f-1a-2b-9d     dinámico\n"
    run_windows = lambda cmd: subprocess.CompletedProcess(cmd, 0, out_windows, "")
    assert lookup_mac("192.168.1.20", runner=run_windows, system="Windows") == "3C:7C:3F:1A:2B:9D"


def test_mac_ausente():
    run_empty = lambda cmd: subprocess.CompletedProcess(cmd, 0, "", "")
    assert lookup_mac("10.8.4.23", runner=run_empty, system="Linux") is None


def test_hostname_falla_sin_romper():
    def boom(ip):
        raise OSError("sin dns")
    assert lookup_hostname("1.2.3.4", resolver=boom) is None


def test_user_agent():
    assert parse_user_agent("Mozilla/5.0 (Windows NT 10.0) Chrome/141.0 Safari/537.36") == ("Chrome", "Windows")
    assert parse_user_agent("Mozilla/5.0 (X11; Linux) Firefox/128.0") == ("Firefox", "Linux")


def test_collect_descarta_mac_de_puerta_de_enlace():
    req = fake_request("192.168.1.20", {"user-agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/141.0"})
    info = collect(req,
        type("S", (), {"trusted_proxies": (), "resolve_hostnames": False})(),
        mac_lookup=lambda ip: "3C:7C:3F:1A:2B:9D",
        hostname_lookup=lambda ip: "PC-01",
        gateway_mac_fn=lambda: "3C:7C:3F:1A:2B:9D"
    )
    assert info.ip == "192.168.1.20"
    assert info.mac is None
    assert info.hostname == "PC-01"
