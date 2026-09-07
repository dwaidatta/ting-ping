"""Ad-hoc traceroute: shells out to the OS's own `tracert`/`traceroute`, the
same way `checks/ping.py` shells out to `ping`, and streams one event per hop
as the subprocess prints it rather than waiting for the whole trace to finish
(a trace can take `max_hops * timeout_s` seconds in the worst case). Nothing
here is scheduled or persisted, unlike the monitors."""

import asyncio
import ipaddress
import platform
import re
import shutil
import socket

from app.netutil import resolve_hostname

_WINDOWS = platform.system() == "Windows"

# Windows tracert (run with -d, so no reverse DNS — hostnames are resolved by
# us afterward): "  3    15 ms    14 ms    14 ms  203.0.113.1", a sub-1ms hop
# ("  1    <1 ms    <1 ms    <1 ms  192.168.1.1"), or one that didn't answer
# ("  2     *        *        *     Request timed out.").
_WIN_HOP_RE = re.compile(
    r"^\s*(\d+)\s+(\*|<?\d+)\s*(?:ms)?\s+(\*|<?\d+)\s*(?:ms)?\s+(\*|<?\d+)\s*(?:ms)?\s+(.+?)\s*$"
)

# IPv6 traces routinely hit hops that never make it to a 3-column RTT line at
# all — ICMPv6 errors print with fewer columns ("  1     *        *     Destination
# host unreachable.", only two stars) or none ("  1  Transmit error: code 1231.").
# The strict 3-column regex above doesn't match either, so without this fallback
# those hops were silently dropped instead of rendered as failed.
_WIN_HOP_FALLBACK_RE = re.compile(r"^\s*(\d+)\s+(.+?)\s*$")

# POSIX traceroute (run with -n, so numeric-only): " 3  203.0.113.1  12.345 ms  12.301 ms  12.250 ms"
# or, on a hop that didn't answer, " 2  * * *".
_POSIX_HOP_RE = re.compile(r"^\s*(\d+)\s+(.+?)\s*$")
_POSIX_RTT_RE = re.compile(r"([\d.]+)\s*ms")
_POSIX_ADDR_RE = re.compile(r"^([0-9a-fA-F.:]+)")


def binary_name() -> str:
    return "tracert" if _WINDOWS else "traceroute"


def binary_missing() -> bool:
    return shutil.which(binary_name()) is None


def resolve_target(host: str, family: str) -> tuple[str, int]:
    """`family` is "auto", "ipv4" or "ipv6". IPv4/IPv6 literals pass straight
    through; a hostname is resolved to the first address of the requested
    family (or any family, for "auto")."""
    host = (host or "").strip()
    if not host:
        raise ValueError("enter a host to trace — a hostname, IPv4, or IPv6 address")

    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        wanted = {"ipv4": 4, "ipv6": 6}.get(family)
        if wanted and addr.version != wanted:
            raise ValueError(f"'{host}' is an IPv{addr.version} address, not IPv{wanted}")
        return host, addr.version

    af = {"ipv4": socket.AF_INET, "ipv6": socket.AF_INET6, "auto": socket.AF_UNSPEC}.get(family, socket.AF_UNSPEC)
    # AI_ALL | AI_V4MAPPED works around Windows (and some other resolvers)
    # silently omitting AAAA records for a host that has them whenever the
    # local machine has no usable IPv6 route of its own — even for an
    # explicit "ipv6" request. Whether *this* machine can route there is what
    # the trace itself is for; DNS resolution shouldn't pre-emptively hide
    # records that exist. For AF_INET/AF_UNSPEC queries the flags are no-ops.
    try:
        infos = socket.getaddrinfo(host, None, af, 0, 0, socket.AI_ALL | socket.AI_V4MAPPED)
    except socket.gaierror as exc:
        raise ValueError(f"could not resolve '{host}': {(exc.strerror or str(exc)).strip()}") from exc

    if family == "ipv6":
        # AI_V4MAPPED also hands back a synthetic "::ffff:a.b.c.d" entry for
        # any A record — not a real IPv6 route, so it doesn't count here.
        infos = [info for info in infos if ipaddress.ip_address(info[4][0]).ipv4_mapped is None]

    if not infos:
        raise ValueError(f"'{host}' has no {family.upper()} address to trace")

    ip = infos[0][4][0]
    version = 6 if infos[0][0] == socket.AF_INET6 else 4
    if family != "auto" and version != (6 if family == "ipv6" else 4):
        raise ValueError(f"'{host}' has no {family.upper()} address to trace")
    return ip, version


def build_command(target_ip: str, version: int, max_hops: int, timeout_s: float) -> list[str]:
    family_flag = "-6" if version == 6 else "-4"
    if _WINDOWS:
        return ["tracert", "-d", family_flag, "-h", str(max_hops), "-w", str(int(timeout_s * 1000)), target_ip]
    return ["traceroute", "-n", family_flag, "-m", str(max_hops), "-w", str(max(1, int(timeout_s))), target_ip]


def _parse_windows_line(line: str) -> dict | None:
    match = _WIN_HOP_RE.match(line)
    if match:
        hop, r1, r2, r3, rest = match.groups()
        rtts = [None if r == "*" else float(r.lstrip("<")) for r in (r1, r2, r3)]
        if "request timed out" in rest.lower():
            return {"hop": int(hop), "ip": None, "rtts_ms": rtts}
        return {"hop": int(hop), "ip": rest.strip(), "rtts_ms": rtts}

    fallback = _WIN_HOP_FALLBACK_RE.match(line)
    if fallback:
        hop, rest = fallback.groups()
        if not rest or rest.lower().startswith(("tracing route", "trace complete")):
            return None
        return {"hop": int(hop), "ip": None, "rtts_ms": [None, None, None]}

    return None


def _parse_posix_line(line: str) -> dict | None:
    match = _POSIX_HOP_RE.match(line)
    if not match:
        return None
    hop, rest = match.groups()
    if rest.strip("* ") == "":
        return {"hop": int(hop), "ip": None, "rtts_ms": [None, None, None]}

    addr_match = _POSIX_ADDR_RE.match(rest)
    if not addr_match:
        return None
    ip = addr_match.group(1)
    rtts = [float(v) for v in _POSIX_RTT_RE.findall(rest)]
    rtts = (rtts + [None, None, None])[:3]
    return {"hop": int(hop), "ip": ip, "rtts_ms": rtts}


def _parse_line(line: str) -> dict | None:
    return _parse_windows_line(line) if _WINDOWS else _parse_posix_line(line)


async def traceroute_stream(target_ip: str, version: int, max_hops: int, timeout_s: float):
    """Yields `{"type": "hop", "hop": {...}}` as each hop is printed, then a
    final `{"type": "done", ...}` once the process exits.

    Same early-stop handling as the discovery sweep/scan: if the caller stops
    consuming early (client disconnects), the `finally` kills the subprocess
    instead of leaving it to trace out every remaining hop in the background.
    """
    cmd = build_command(target_ip, version, max_hops, timeout_s)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
    except FileNotFoundError:
        yield {"type": "error", "message": f"'{binary_name()}' command not found on this machine"}
        return

    reached = False
    try:
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            parsed = _parse_line(raw.decode(errors="ignore").rstrip("\n"))
            if not parsed:
                continue

            if parsed["ip"]:
                parsed["hostname"] = await resolve_hostname(parsed["ip"])
                if parsed["ip"] == target_ip:
                    parsed["reached"] = True
                    reached = True
            else:
                parsed["hostname"] = None

            yield {"type": "hop", "hop": parsed}

        await proc.wait()
        yield {"type": "done", "target_ip": target_ip, "reached": reached}
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
