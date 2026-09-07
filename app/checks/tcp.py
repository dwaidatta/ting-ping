import asyncio
import time

from app.checks.status import CheckStatus, classify_oserror
from app.config import settings


async def run_tcp_check(target) -> tuple[CheckStatus, float | None, str]:
    if not target.tcp_port:
        return CheckStatus.CONFIG_ERROR, None, "no TCP port configured for this monitor"

    start = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(target.host, target.tcp_port),
            timeout=settings.tcp_timeout_s,
        )
        writer.close()
        await writer.wait_closed()
        return CheckStatus.OK, (time.monotonic() - start) * 1000, f"port {target.tcp_port} accepted the connection"
    except asyncio.TimeoutError:
        return CheckStatus.TIMEOUT, None, f"no response from port {target.tcp_port} within {settings.tcp_timeout_s:g}s"
    except OSError as exc:
        return classify_oserror(exc), None, _reason(exc)


def _reason(exc: OSError) -> str:
    text = getattr(exc, "strerror", None) or str(exc)
    return text.strip() or exc.__class__.__name__
