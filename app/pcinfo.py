from __future__ import annotations

import functools
import ipaddress
import os
import platform
import re
import subprocess
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass(frozen=True)
class ClientInfo:
    ip: str = ""
    mac: Optional[str] = None
    hostname: Optional[str] = None
    browser: str = "Navegador"
    os: str = "Desconocido"
    user_agent: str = ""


def client_ip(request, trusted_proxies) -> str:
    headers = {k.lower(): v.split(",") for k, v in request.headers.items()}
    peer = str(request.client.host) if request.client else "0.0.0.0"
    trusted = []
    for net in trusted_proxies:
        try:
            trusted.append(ipaddress.ip_network(str(net)))
        except Exception:
            continue
    if not trusted:
        return peer
    xff_values = headers.get("x-forwarded-for", [])
    for h in xff_values:
        try:
            cand = ipaddress.ip_address(h.strip())
        except ValueError:
            continue
        if not any(cand in net for net in trusted):
            return h.strip()
    return peer


def lookup_mac(ip: str, *, runner: Optional[Callable] = None, system: Optional[str] = None) -> Optional[str]:
    system = system or platform.system()
    if system == "Linux":
        cmd = ["ip", "neigh", "show", ip]
    elif system == "Windows":
        cmd = ["arp", "-a", ip]
    else:
        cmd = ["ip", "neigh", "show", ip]
    try:
        output = (runner(cmd) if runner is not None else subprocess.run(
            cmd, text=True, capture_output=True, timeout=5
        )).stdout
    except Exception:
        output = ""
    pattern = re.compile(r"([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}")
    match = pattern.search(output or "")
    if match:
        mac = match.group(0).replace("-", ":").replace(".", ":").upper()
        return mac
    return None


def lookup_hostname(ip: str, *, resolver=socket.gethostbyaddr, timeout: float = 1.0) -> Optional[str]:
    resolver = resolver or socket.gethostbyaddr
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(resolver, ip)
        try:
            return future.result(timeout=timeout)
        except (OSError, TimeoutError, Exception):
            return None


@functools.lru_cache(maxsize=1)
def default_gateway_mac(*, runner=None, system=None) -> Optional[str]:
    system = system or platform.system()
    try:
        if system == "Windows":
            shell = (
                'powershell -NoProfile -Command '
                '"(Get-NetRoute -DestinationPrefix 0.0.0.0/0 | '
                'Select-Object -First 1).NextHop"'
            )
            cmd = ["powershell", "-NoProfile", "-Command", shell]
            output = (runner(cmd) if runner is not None else subprocess.run(cmd, text=True, capture_output=True, timeout=5)).stdout
        else:
            cmd = ["ip", "route", "show", "default"]
            output = (runner(cmd) if runner is not None else subprocess.run(cmd, text=True, capture_output=True, timeout=5)).stdout
        first_line = next((line.strip() for line in output.splitlines() if line.strip()), "")
        match = re.search(r"\b((?:[\dA-Fa-f]{2}[:\-.]){3}[\dA-Fa-f]{2})\b", first_line)
        if match:
            return match.group(0).replace("-", ":").upper()
    except Exception:
        pass
    return None


def parse_user_agent(ua: str) -> tuple[str, str]:
    browser = "Navegador"
    os_name = "Desconocido"
    if ua:
        lower = ua.lower()
        if "edg/" in lower or "edge" in lower:
            browser = "Edge"
        elif "chrome/" in lower or "chromium" in lower:
            browser = "Chrome"
        elif "firefox/" in lower:
            browser = "Firefox"
        elif "safari/" in lower:
            browser = "Safari"
    if ua:
        lower = ua.lower()
        if "windows nt" in lower:
            os_name = "Windows"
        elif "linux" in lower:
            os_name = "Linux"
        elif "mac os x" in lower or "macos" in lower:
            os_name = "macOS"
    return (browser, os_name)


def collect(request, settings, *, mac_lookup=None, hostname_lookup=None, gateway_mac_fn=None) -> ClientInfo:
    ip = client_ip(request, settings.trusted_proxies)
    ua = request.headers.get("user-agent", "")
    browser, os_name = parse_user_agent(ua)
    hostname = None
    mac = None
    if settings.resolve_hostnames or hostname_lookup is not None:
        try:
            hostname = hostname_lookup(ip) if hostname_lookup else lookup_hostname(ip)
        except Exception:
            hostname = None
    try:
        mac = mac_lookup(ip) if mac_lookup else lookup_mac(ip)
    except Exception:
        mac = None
    if gateway_mac_fn is not None and mac is not None:
        if mac == gateway_mac_fn():
            mac = None
    return ClientInfo(ip=ip, mac=mac, hostname=hostname, browser=browser, os=os_name, user_agent=ua)
