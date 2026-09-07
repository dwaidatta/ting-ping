"""Ad-hoc DNS lookups triggered by hand from the resolver page: forward
(hostname -> addresses) and reverse (address -> hostname), both IPv4 and
IPv6. Nothing here is scheduled or persisted, unlike the monitors' own DNS
check in `checks/dns.py`, which this mirrors."""

import asyncio
import ipaddress
import socket
import time

from app.config import settings


async def _reverse(ip: str, version: int) -> dict:
    try:
        hostname, _, _ = await asyncio.wait_for(
            asyncio.to_thread(socket.gethostbyaddr, ip), timeout=settings.dns_timeout_s
        )
    except asyncio.TimeoutError:
        raise ValueError(f"reverse lookup of {ip} did not answer within {settings.dns_timeout_s:g}s")
    except socket.herror:
        return {"type": "ip", "query": ip, "version": version, "hostname": None}
    except OSError as exc:
        raise ValueError(f"reverse lookup of {ip} failed: {(getattr(exc, 'strerror', None) or str(exc)).strip()}")

    return {"type": "ip", "query": ip, "version": version, "hostname": hostname}


async def _forward(host: str) -> dict:
    start = time.monotonic()
    try:
        infos = await asyncio.wait_for(
            asyncio.to_thread(socket.getaddrinfo, host, None, socket.AF_UNSPEC, 0, 0, socket.AI_CANONNAME),
            timeout=settings.dns_timeout_s,
        )
    except asyncio.TimeoutError:
        raise ValueError(f"'{host}' did not resolve within {settings.dns_timeout_s:g}s")
    except socket.gaierror as exc:
        raise ValueError(f"could not resolve '{host}': {(exc.strerror or str(exc)).strip()}")

    ipv4: list[str] = []
    ipv6: list[str] = []
    canonical_name = None
    for family, _, _, canonname, sockaddr in infos:
        if canonname and not canonical_name:
            canonical_name = canonname
        address = sockaddr[0]
        target = ipv6 if family == socket.AF_INET6 else ipv4
        if address not in target:
            target.append(address)

    return {
        "type": "hostname",
        "query": host,
        "canonical_name": canonical_name if canonical_name and canonical_name != host else None,
        "latency_ms": (time.monotonic() - start) * 1000,
        "addresses": {"ipv4": ipv4, "ipv6": ipv6},
    }


async def resolve_query(query: str) -> dict:
    query = (query or "").strip()
    if not query:
        raise ValueError("enter a hostname or IP address to resolve")

    try:
        addr = ipaddress.ip_address(query)
    except ValueError:
        return await _forward(query)
    return await _reverse(query, addr.version)
