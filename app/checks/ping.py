import asyncio
import platform
import re

from app.checks.status import CheckStatus
from app.config import settings

_WINDOWS = platform.system() == "Windows"
_LATENCY_RE = re.compile(r"time[=<]\s*([\d.]+)\s*ms", re.IGNORECASE)

# Ordered: the first phrase found in the ping output wins. Ping reports failures in
# its text rather than its exit code — on Windows a "destination host unreachable"
# reply even exits 0 — so the output is the authority, not the return code.
_OUTPUT_SIGNS: list[tuple[re.Pattern, CheckStatus]] = [
    (re.compile(r"could not find host|unknown host|name or service not known|"
                r"temporary failure in name resolution", re.I), CheckStatus.DNS_FAILURE),
    (re.compile(r"ttl expired", re.I), CheckStatus.TTL_EXPIRED),
    (re.compile(r"destination (host|net|network|port|protocol) unreachable", re.I), CheckStatus.UNREACHABLE),
    (re.compile(r"network is unreachable|transmit failed", re.I), CheckStatus.NETWORK_DOWN),
    (re.compile(r"request timed out|100% packet loss|100\.0% packet loss", re.I), CheckStatus.TIMEOUT),
    (re.compile(r"operation not permitted|permission denied", re.I), CheckStatus.PERMISSION_DENIED),
    (re.compile(r"general failure", re.I), CheckStatus.GENERAL_FAILURE),
]


def _classify_output(text: str) -> CheckStatus | None:
    for pattern, status in _OUTPUT_SIGNS:
        if pattern.search(text):
            return status
    return None


async def run_ping_check(target) -> tuple[CheckStatus, float | None, str]:
    if _WINDOWS:
        cmd = ["ping", "-n", "1", "-w", str(int(settings.ping_timeout_s * 1000)), target.host]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, int(settings.ping_timeout_s))), target.host]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=settings.ping_timeout_s + 1
        )
    except asyncio.TimeoutError:
        return CheckStatus.TIMEOUT, None, "ping did not return in time"
    except FileNotFoundError:
        return CheckStatus.CONFIG_ERROR, None, "ping command not found on this machine"

    text = (stdout.decode(errors="ignore") + stderr.decode(errors="ignore")).strip()

    reported = _classify_output(text)
    if reported is not None:
        return reported, None, _first_meaningful_line(text)

    if proc.returncode != 0:
        return CheckStatus.UNREACHABLE, None, _first_meaningful_line(text) or "no reply"

    match = _LATENCY_RE.search(text)
    latency = float(match.group(1)) if match else None
    return CheckStatus.OK, latency, "reply received"


def _first_meaningful_line(text: str) -> str:
    """The line ping itself printed, so the card can quote the real message."""
    for line in text.splitlines():
        line = line.strip()
        if line and not line.lower().startswith(("pinging", "ping statistics", "---")):
            return line
    return ""
