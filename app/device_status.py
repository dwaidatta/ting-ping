"""Reads this machine's real network state.

Everything here comes from the operating system itself — `ipconfig /all` and
`netsh` on Windows, `ip`/`resolv.conf` on POSIX, psutil for adapter counters —
parsed per adapter so a VPN or a second NIC cannot have its gateway and DNS
servers attributed to the physical link. The one outbound call is the optional
public-IP lookup, which is what tells you how the internet sees you.
"""

import asyncio
import os
import platform
import re
import socket
import subprocess
import time

import psutil

from app.checks.status import CheckStatus
from app.checks.tcp import run_tcp_check
from app.config import settings
from app.models import Target, CheckMethod

_WINDOWS = platform.system() == "Windows"

_VPN_NAME_HINTS = ("tun", "tap", "ppp", "wg", "utun", "vpn", "nordlynx", "wintun", "zerotier", "tailscale")

# Previous byte counters, so a snapshot can report a rate and not just a total.
_last_counters: dict[str, tuple[float, int, int]] = {}

# Public IP is cached briefly: refreshing the panel should not hammer a third party.
_public_ip_cache: tuple[float, dict] | None = None
_PUBLIC_IP_TTL_S = 30.0
# A failure is cached far more briefly than a success: one dropped request should
# not leave the panel reading "lookup failed" for half a minute, least of all when
# someone has just pressed refresh.
_PUBLIC_IP_ERROR_TTL_S = 3.0


def _run_text(cmd: list[str], timeout: int = 5) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=timeout, text=True, errors="ignore")
        return out.stdout or ""
    except Exception:
        return ""


# ── windows: parse ipconfig /all into one dict per adapter ──────────────────

_ADAPTER_RE = re.compile(r"^(?P<kind>[\w\- ]+adapter) (?P<name>.+):\s*$", re.IGNORECASE)
_FIELD_RE = re.compile(r"^\s{2,}(?P<key>[\w\-,/ ]+?)[\s.]*:\s?(?P<value>.*)$")


def _parse_ipconfig(text: str) -> tuple[dict, dict[str, dict]]:
    """Split `ipconfig /all` into (global header fields, {adapter name: fields}).

    Multi-line values (extra DNS servers, extra IPv6 addresses) are folded onto
    the key they belong to, which is what the old single-regex parser lost.
    """
    header: dict[str, list[str]] = {}
    adapters: dict[str, dict[str, list[str]]] = {}

    current: dict[str, list[str]] = header
    current_kind = ""
    last_key: str | None = None

    for raw in text.splitlines():
        if not raw.strip():
            continue

        adapter = _ADAPTER_RE.match(raw)
        if adapter:
            name = adapter.group("name").strip()
            current = adapters.setdefault(name, {})
            current["__kind__"] = [adapter.group("kind").strip()]
            current_kind = name
            last_key = None
            continue

        field = _FIELD_RE.match(raw)
        if field:
            key = field.group("key").strip().lower()
            value = field.group("value").strip()
            current.setdefault(key, [])
            if value:
                current[key].append(value)
            last_key = key
            continue

        # An indented bare value continues the previous key.
        if last_key and raw.startswith(" ") and raw.strip():
            current.setdefault(last_key, []).append(raw.strip())

    del current_kind
    return header, adapters


def _clean_addr(value: str) -> str:
    """`192.168.1.2(Preferred)` -> `192.168.1.2`; strips IPv6 zone ids too."""
    return re.sub(r"\(.*?\)", "", value).split("%")[0].strip()


def _first(fields: dict, *keys: str) -> str | None:
    for key in keys:
        values = fields.get(key)
        if values:
            cleaned = _clean_addr(values[0])
            if cleaned:
                return cleaned
    return None


def _all_values(fields: dict, *keys: str) -> list[str]:
    out: list[str] = []
    for key in keys:
        for value in fields.get(key, []):
            cleaned = _clean_addr(value)
            if cleaned and cleaned not in out:
                out.append(cleaned)
    return out


def _windows_snapshot() -> dict:
    header, adapters = _parse_ipconfig(_run_text(["ipconfig", "/all"]))

    # The active adapter is the one that actually has a default gateway and an
    # address — not merely the first block in the output.
    chosen_name, chosen = None, {}
    for name, fields in adapters.items():
        gateway = _first(fields, "default gateway")
        address = _first(fields, "ipv4 address", "autoconfiguration ipv4 address")
        if gateway and address and not address.startswith("169.254"):
            chosen_name, chosen = name, fields
            break

    if chosen_name is None:
        for name, fields in adapters.items():
            if _first(fields, "ipv4 address"):
                chosen_name, chosen = name, fields
                break

    return {
        "iface": chosen_name,
        "hostname": _first(header, "host name"),
        "dns_suffix": _first(chosen, "connection-specific dns suffix") or _first(header, "primary dns suffix"),
        "description": _first(chosen, "description"),
        "address": _first(chosen, "ipv4 address", "autoconfiguration ipv4 address"),
        "netmask": _first(chosen, "subnet mask"),
        "gateway": _first(chosen, "default gateway"),
        "dns_servers": _all_values(chosen, "dns servers"),
        "dhcp": _first(chosen, "dhcp enabled"),
        "dhcp_server": _first(chosen, "dhcp server"),
        "lease_expires": _first(chosen, "lease expires"),
        "ipv6": [
            a for a in _all_values(chosen, "ipv6 address", "temporary ipv6 address")
            if not a.lower().startswith("fe80")
        ],
        "link_local": _first(chosen, "link-local ipv6 address"),
        "adapter_kind": _first(chosen, "__kind__"),
    }


def _posix_snapshot() -> dict:
    gateway = None
    out = _run_text(["ip", "route"])
    match = re.search(r"default via ([\d.]+)", out)
    if match:
        gateway = match.group(1)

    if not gateway:
        match = re.search(r"gateway:\s*([\d.]+)", _run_text(["route", "-n", "get", "default"]))
        if match:
            gateway = match.group(1)

    dns_servers: list[str] = []
    try:
        with open("/etc/resolv.conf", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = re.match(r"nameserver\s+([\d.:a-fA-F]+)", line.strip())
                if m and m.group(1) not in dns_servers:
                    dns_servers.append(m.group(1))
    except Exception:
        pass

    return {
        "iface": None,
        "hostname": socket.gethostname(),
        "dns_suffix": None,
        "description": None,
        "address": None,
        "netmask": None,
        "gateway": gateway,
        "dns_servers": dns_servers,
        "dhcp": None,
        "dhcp_server": None,
        "lease_expires": None,
        "ipv6": [],
        "link_local": None,
        "adapter_kind": None,
    }


def _os_snapshot() -> dict:
    return _windows_snapshot() if _WINDOWS else _posix_snapshot()


# ── psutil fills in whatever the OS text output did not ─────────────────────


def _active_interface_name(snapshot: dict) -> str | None:
    if snapshot.get("iface") and snapshot["iface"] in psutil.net_if_addrs():
        return snapshot["iface"]

    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()
    up = [name for name, s in stats.items() if s.isup and "loopback" not in name.lower()]

    gateway = snapshot.get("gateway")
    if gateway:
        for name in up:
            for a in addrs.get(name, []):
                if a.family == socket.AF_INET and a.address:
                    try:
                        if _same_subnet(a.address, a.netmask, gateway):
                            return name
                    except Exception:
                        continue

    for name in up:
        for a in addrs.get(name, []):
            if a.family == socket.AF_INET and not a.address.startswith("169.254"):
                return name

    return up[0] if up else None


def _same_subnet(ip: str, netmask: str | None, other: str) -> bool:
    if not netmask or ":" in ip or ":" in other:
        return False
    ip_parts = [int(x) for x in ip.split(".")]
    mask_parts = [int(x) for x in netmask.split(".")]
    other_parts = [int(x) for x in other.split(".")]
    return all((ip_parts[i] & mask_parts[i]) == (other_parts[i] & mask_parts[i]) for i in range(4))


def _ipv4_info(iface: str | None, snapshot: dict) -> dict:
    address, netmask = snapshot.get("address"), snapshot.get("netmask")
    broadcast = None

    if iface:
        for a in psutil.net_if_addrs().get(iface, []):
            if a.family == socket.AF_INET:
                address = address or a.address
                netmask = netmask or a.netmask
                broadcast = a.broadcast
                break

    return {
        "address": address,
        "netmask": netmask,
        "cidr": _cidr(address, netmask),
        "broadcast": broadcast,
        "gateway": snapshot.get("gateway"),
        "dhcp": snapshot.get("dhcp"),
        "dhcp_server": snapshot.get("dhcp_server"),
        "lease_expires": snapshot.get("lease_expires"),
    }


def _cidr(address: str | None, netmask: str | None) -> str | None:
    if not address or not netmask or ":" in address:
        return None
    try:
        bits = sum(bin(int(part)).count("1") for part in netmask.split("."))
        network = ".".join(
            str(int(a) & int(m)) for a, m in zip(address.split("."), netmask.split("."))
        )
        return f"{network}/{bits}"
    except Exception:
        return None


def _ipv6_info(iface: str | None, snapshot: dict) -> dict:
    addresses = list(snapshot.get("ipv6") or [])
    link_local = snapshot.get("link_local")

    if iface:
        for a in psutil.net_if_addrs().get(iface, []):
            if a.family == socket.AF_INET6:
                addr = a.address.split("%")[0]
                if addr.startswith("fe80"):
                    link_local = link_local or addr
                elif addr not in addresses:
                    addresses.append(addr)

    return {"addresses": addresses, "link_local": link_local, "enabled": bool(addresses or link_local)}


def _interface_info(iface: str | None, snapshot: dict) -> dict:
    if not iface:
        return {"name": None, "mac": None, "isup": False, "description": snapshot.get("description")}

    stats = psutil.net_if_stats().get(iface)
    mac = None
    for a in psutil.net_if_addrs().get(iface, []):
        if a.family == psutil.AF_LINK:
            mac = a.address

    return {
        "name": iface,
        "description": snapshot.get("description"),
        "kind": snapshot.get("adapter_kind"),
        "mac": mac,
        "isup": stats.isup if stats else False,
        "speed_mbps": stats.speed if stats else None,
        "mtu": stats.mtu if stats else None,
        "duplex": _duplex_label(stats.duplex) if stats else None,
    }


def _duplex_label(duplex) -> str | None:
    return {
        psutil.NIC_DUPLEX_FULL: "full",
        psutil.NIC_DUPLEX_HALF: "half",
        psutil.NIC_DUPLEX_UNKNOWN: None,
    }.get(duplex)


def _traffic_counters(iface: str | None) -> dict:
    if not iface:
        return {}
    counters = psutil.net_io_counters(pernic=True).get(iface)
    if not counters:
        return {}

    now = time.monotonic()
    sent_rate = recv_rate = None
    previous = _last_counters.get(iface)
    if previous:
        elapsed = now - previous[0]
        if elapsed > 0.5:
            sent_rate = max(0, counters.bytes_sent - previous[1]) / elapsed
            recv_rate = max(0, counters.bytes_recv - previous[2]) / elapsed
    _last_counters[iface] = (now, counters.bytes_sent, counters.bytes_recv)

    return {
        "bytes_sent": counters.bytes_sent,
        "bytes_recv": counters.bytes_recv,
        "packets_sent": counters.packets_sent,
        "packets_recv": counters.packets_recv,
        "errin": counters.errin,
        "errout": counters.errout,
        "dropin": counters.dropin,
        "dropout": counters.dropout,
        "send_rate_bps": sent_rate,
        "recv_rate_bps": recv_rate,
    }


# ── wireless ────────────────────────────────────────────────────────────────


def _wifi_info(iface: str | None) -> dict | None:
    """SSID and radio detail, when the active adapter is a wireless one."""
    if not _WINDOWS:
        return None

    text = _run_text(["netsh", "wlan", "show", "interfaces"])
    if not text.strip():
        return None

    blocks = re.split(r"\n(?=\s*Name\s*:)", text)
    for block in blocks:
        name = re.search(r"^\s*Name\s*:\s*(.+)$", block, re.M)
        if not name:
            continue
        if iface and name.group(1).strip() != iface:
            continue

        def grab(label: str) -> str | None:
            m = re.search(rf"^\s*{label}\s*:\s*(.+)$", block, re.M)
            return m.group(1).strip() if m else None

        state = grab("State")
        if state and state.lower() != "connected":
            return None
        return {
            "ssid": grab("SSID"),
            "bssid": grab("BSSID"),
            "signal": grab("Signal"),
            "radio": grab("Radio type"),
            "band": grab("Band"),
            "channel": grab("Channel"),
            "auth": grab("Authentication"),
            "rx_mbps": grab(r"Receive rate \(Mbps\)"),
            "tx_mbps": grab(r"Transmit rate \(Mbps\)"),
        }
    return None


# ── reachability + public identity ──────────────────────────────────────────


async def _probe(host: str, port: int) -> tuple[bool | None, float | None, str]:
    probe = Target(
        id="__device_probe__",
        name=host,
        host=host,
        method=CheckMethod.TCP,
        interval_s=1,
        tcp_port=port,
    )
    status, latency, detail = await run_tcp_check(probe)
    return status == CheckStatus.OK, latency, detail


async def _gateway_reachable(gateway: str | None) -> dict:
    if not gateway:
        return {"reachable": None, "latency_ms": None, "detail": "no default gateway configured"}
    ok, latency, detail = await _probe(gateway, settings.gateway_probe_port)
    return {"reachable": ok, "latency_ms": latency, "detail": detail}


async def _internet_reachable() -> dict:
    host, port = settings.internet_probe_host, settings.internet_probe_port
    ok, latency, detail = await _probe(host, port)
    return {"reachable": ok, "latency_ms": latency, "detail": detail, "probe": f"{host}:{port}"}


async def _public_ip() -> dict:
    """How the internet sees this machine. Requires one outbound request."""
    global _public_ip_cache

    if not settings.public_ip_lookup:
        return {"enabled": False, "reason": "disabled by TP_PUBLIC_IP_LOOKUP=0"}

    if _public_ip_cache:
        age = time.monotonic() - _public_ip_cache[0]
        ttl = _PUBLIC_IP_ERROR_TTL_S if _public_ip_cache[1].get("error") else _PUBLIC_IP_TTL_S
        if age < ttl:
            return _public_ip_cache[1]

    from app.checks.http import get_client

    client = get_client()
    if client is None:
        return {"enabled": True, "error": "HTTP client not initialised"}

    try:
        resp = await client.get(settings.public_ip_url, timeout=settings.public_ip_timeout_s)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        result = {"enabled": True, "error": f"lookup failed: {type(exc).__name__}"}
        _public_ip_cache = (time.monotonic(), result)
        return result

    city, region = payload.get("city"), payload.get("region")
    location = ", ".join(p for p in (city, region, payload.get("country")) if p)

    result = {
        "enabled": True,
        "ip": payload.get("ip"),
        "hostname": payload.get("hostname"),
        "org": payload.get("org"),
        "location": location or None,
        "timezone": payload.get("timezone"),
        "source": settings.public_ip_url,
    }
    _public_ip_cache = (time.monotonic(), result)
    return result


def _dns_test() -> dict:
    start = time.monotonic()
    try:
        infos = socket.getaddrinfo(settings.dns_probe_host, None)
        addresses = sorted({info[4][0] for info in infos})
        return {
            "success": True,
            "latency_ms": (time.monotonic() - start) * 1000,
            "host": settings.dns_probe_host,
            "resolved": addresses[:2],
        }
    except socket.gaierror as exc:
        return {
            "success": False,
            "latency_ms": None,
            "host": settings.dns_probe_host,
            "error": (exc.strerror or str(exc)).strip(),
        }


def _host_info() -> dict:
    boot = psutil.boot_time()
    return {
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "uptime_s": max(0, time.time() - boot),
    }


def _vpn_or_proxy_suspected(iface: str | None, public: dict) -> dict:
    reasons = []

    if iface and any(hint in iface.lower() for hint in _VPN_NAME_HINTS):
        reasons.append(f"adapter name '{iface}' looks like a tunnel")

    proxy_vars = [v for v in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
                  if os.environ.get(v)]
    if proxy_vars:
        reasons.append(f"proxy environment variable set ({', '.join(sorted(set(v.lower() for v in proxy_vars)))})")

    tunnels = [name for name in psutil.net_if_stats()
               if any(hint in name.lower() for hint in _VPN_NAME_HINTS)
               and psutil.net_if_stats()[name].isup]
    if tunnels:
        reasons.append(f"tunnel adapter up ({', '.join(tunnels)})")

    org = (public or {}).get("org") or ""
    if any(word in org.lower() for word in ("vpn", "proxy", "hosting", "datacenter", "data center")):
        reasons.append(f"public IP belongs to '{org.strip()}'")

    return {"suspected": bool(reasons), "reasons": reasons, "heuristic": True}


async def compute_device_status() -> dict:
    snapshot = await asyncio.to_thread(_os_snapshot)
    iface = await asyncio.to_thread(_active_interface_name, snapshot)

    dns_test, wifi, gateway, internet, public = await asyncio.gather(
        asyncio.to_thread(_dns_test),
        asyncio.to_thread(_wifi_info, iface),
        _gateway_reachable(snapshot.get("gateway")),
        _internet_reachable(),
        _public_ip(),
    )

    return {
        "read_at": time.time(),
        "host": {**_host_info(), "dns_suffix": snapshot.get("dns_suffix")},
        "ipv4": _ipv4_info(iface, snapshot),
        "ipv6": _ipv6_info(iface, snapshot),
        "dns": {"servers": snapshot.get("dns_servers") or [], "test": dns_test},
        "interface": _interface_info(iface, snapshot),
        "wifi": wifi,
        "traffic": _traffic_counters(iface),
        "public": public,
        "connectivity": {
            "gateway": gateway,
            "internet": internet,
            "vpn_or_proxy": _vpn_or_proxy_suspected(iface, public),
        },
    }
