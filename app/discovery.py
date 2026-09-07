"""Ad-hoc network discovery: sweep a subnet for hosts that answer, or probe
one host across a set of ports.

Both are triggered by hand from the discovery page and run once — nothing
here is scheduled or persisted, unlike the monitors. Host sweeps reuse the
same subprocess `ping` the monitor ping check uses, so results follow the
same fixed vocabulary; port scans open raw TCP connections directly since
there is no per-port "monitor" to route through.
"""

import asyncio
import ipaddress
import re
import socket
import subprocess
import time

from app.checks.ping import run_ping_check
from app.checks.status import CheckStatus
from app.config import settings
from app.models import CheckMethod, Target
from app.netutil import resolve_hostname

_MAC_RE = re.compile(r"([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}")
_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_PORT_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


class ConfirmRequired(ValueError):
    """A range is large enough to be worth a second thought, but not so large
    it has to be rejected outright — the caller re-sends with `force=True`
    once the user has confirmed they want to go ahead anyway."""


# ── network sweep ────────────────────────────────────────────────────────────


def parse_ipv4_subnet(subnet: str, force: bool = False) -> "ipaddress.IPv4Network":
    subnet = (subnet or "").strip()
    if not subnet:
        raise ValueError("enter an IPv4 subnet in CIDR form, e.g. 192.168.1.0/24")
    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError as exc:
        raise ValueError(f"'{subnet}' is not a valid subnet in CIDR form, e.g. 192.168.1.0/24") from exc
    if network.version != 4:
        raise ValueError("only IPv4 subnets can be swept — enter a range like 192.168.1.0/24")
    if network.num_addresses > settings.discovery_hard_max_hosts:
        raise ValueError(
            f"{subnet} has {network.num_addresses} addresses, more than the "
            f"{settings.discovery_hard_max_hosts}-host hard limit — try a smaller range"
        )
    if not force and network.num_addresses > settings.discovery_warn_hosts:
        raise ConfirmRequired(
            f"{subnet} has {network.num_addresses} addresses — sweeping this many hosts "
            f"could take a while. Scan anyway?"
        )
    return network


async def _probe_host(ip: str, sem: asyncio.Semaphore) -> dict | None:
    probe = Target(id="__discovery__", name=ip, host=ip, method=CheckMethod.PING, interval_s=1)
    async with sem:
        status, latency_ms, _ = await run_ping_check(probe)
    if status != CheckStatus.OK:
        return None
    hostname = await resolve_hostname(ip)
    return {"ip": ip, "hostname": hostname, "latency_ms": latency_ms, "mac": None}


def _read_arp_table() -> dict[str, str]:
    """Best-effort ip -> mac from this machine's own ARP cache.

    The ping sweep that precedes this populates the cache for anything on the
    local link; addresses beyond the local router will simply have no entry.
    """
    try:
        out = subprocess.run(
            ["arp", "-a"], capture_output=True, timeout=5, text=True, errors="ignore"
        ).stdout
    except Exception:
        return {}

    table: dict[str, str] = {}
    for line in out.splitlines():
        ip_match = _IP_RE.search(line)
        mac_match = _MAC_RE.search(line)
        if ip_match and mac_match:
            table[ip_match.group(0)] = mac_match.group(0).replace("-", ":").lower()
    return table


async def sweep_subnet_stream(network: "ipaddress.IPv4Network"):
    """Probes every host in `network` concurrently and yields each one the moment
    it answers, so a caller can render results as they arrive instead of waiting
    for the whole sweep to finish. Finishes with one `done` event carrying the
    full, sorted list with MAC addresses filled in (a single `arp -a` covers all
    of them at once, so that lookup happens after the pings rather than per-host).

    If the caller stops consuming early (the client disconnects, e.g. a "stop
    scan" button), Starlette cancels whichever `await` is in flight here — the
    `finally` below cancels every still-running probe so a stopped scan doesn't
    keep pinging in the background."""
    sem = asyncio.Semaphore(settings.discovery_sweep_concurrency)
    tasks = [asyncio.create_task(_probe_host(str(ip), sem)) for ip in network.hosts()]

    hosts: list[dict] = []
    try:
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result:
                hosts.append(result)
                yield {"type": "host", "host": result}

        if hosts:
            mac_table = await asyncio.to_thread(_read_arp_table)
            for host in hosts:
                host["mac"] = mac_table.get(host["ip"])

        hosts.sort(key=lambda h: ipaddress.ip_address(h["ip"]))
        yield {"type": "done", "hosts": hosts}
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()


# ── port scan ─────────────────────────────────────────────────────────────────


def resolve_scan_host(host: str) -> str:
    """IPv4/IPv6 literals pass straight through; anything else is resolved as
    a hostname, the same way a monitor's host field accepts either."""
    host = (host or "").strip()
    if not host:
        raise ValueError("enter an IPv4 or IPv6 address to scan")
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    try:
        return socket.getaddrinfo(host, None)[0][4][0]
    except socket.gaierror as exc:
        raise ValueError(f"could not resolve '{host}': {(exc.strerror or str(exc)).strip()}") from exc


def parse_ports(spec: str, force: bool = False) -> list[int]:
    ports: set[int] = set()
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue

        range_match = _PORT_RANGE_RE.match(part)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            if not (1 <= start <= 65535 and 1 <= end <= 65535 and start <= end):
                raise ValueError(f"'{part}' is not a valid port range (1-65535)")
            ports.update(range(start, end + 1))
        elif part.isdigit():
            port = int(part)
            if not (1 <= port <= 65535):
                raise ValueError(f"port {port} is out of range (1-65535)")
            ports.add(port)
        else:
            raise ValueError(f"'{part}' is not a valid port or port range")

    if not ports:
        raise ValueError("enter at least one port, a range, or a comma list, e.g. 22,80,443 or 1-1024")
    if len(ports) > settings.discovery_max_ports:
        raise ValueError(
            f"{len(ports)} ports requested, more than the {settings.discovery_max_ports}-port scan limit"
        )
    if not force and len(ports) > settings.discovery_warn_ports:
        raise ConfirmRequired(
            f"{len(ports)} ports requested — scanning this many could take a while. Scan anyway?"
        )
    return sorted(ports)


def _service_name(port: int) -> str | None:
    try:
        return socket.getservbyport(port, "tcp")
    except OSError:
        return None


async def _scan_one_port(host: str, port: int, sem: asyncio.Semaphore) -> dict:
    async with sem:
        start = time.monotonic()
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=settings.port_scan_timeout_s
            )
        except ConnectionRefusedError:
            return {"port": port, "state": "closed", "service": _service_name(port), "latency_ms": None}
        except (asyncio.TimeoutError, OSError):
            return {"port": port, "state": "filtered", "service": _service_name(port), "latency_ms": None}

        latency_ms = (time.monotonic() - start) * 1000
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass
        return {"port": port, "state": "open", "service": _service_name(port), "latency_ms": latency_ms}


async def scan_ports_stream(ip: str, ports: list[int]):
    """Probes every port concurrently and yields each result the moment it
    completes, then a final `done` event carrying the full list sorted by
    port number — the same shape `sweep_subnet_stream` uses for host sweeps.

    Same early-stop handling as `sweep_subnet_stream`: if the client
    disconnects (a "stop scan" click), the `finally` cancels whichever port
    probes are still open instead of letting them run to completion unseen."""
    sem = asyncio.Semaphore(settings.discovery_port_concurrency)
    tasks = [asyncio.create_task(_scan_one_port(ip, port, sem)) for port in ports]

    results: list[dict] = []
    try:
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            yield {"type": "port", "port": result}

        results.sort(key=lambda r: r["port"])
        yield {"type": "done", "ports": results}
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
