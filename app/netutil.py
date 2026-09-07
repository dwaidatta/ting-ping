"""Small helpers shared by the on-demand network tools (discovery, traceroute) —
nothing here is scheduled or persisted, unlike the monitor checks."""

import asyncio
import socket


async def resolve_hostname(ip: str, timeout_s: float = 1.5) -> str | None:
    """Best-effort reverse DNS; None (not an error) when there's no PTR record."""
    try:
        host, _, _ = await asyncio.wait_for(asyncio.to_thread(socket.gethostbyaddr, ip), timeout=timeout_s)
        return host
    except Exception:
        return None
