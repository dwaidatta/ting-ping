import asyncio
import socket
import time

from app.checks.status import CheckStatus
from app.config import settings


async def run_dns_check(target) -> tuple[CheckStatus, float | None, str]:
    start = time.monotonic()
    try:
        infos = await asyncio.wait_for(
            asyncio.to_thread(socket.getaddrinfo, target.host, None),
            timeout=settings.dns_timeout_s,
        )
    except asyncio.TimeoutError:
        return CheckStatus.TIMEOUT, None, f"resolver did not answer within {settings.dns_timeout_s:g}s"
    except socket.gaierror as exc:
        return CheckStatus.DNS_FAILURE, None, (exc.strerror or str(exc)).strip()
    except OSError as exc:
        return CheckStatus.GENERAL_FAILURE, None, (getattr(exc, "strerror", None) or str(exc)).strip()

    addresses = sorted({info[4][0] for info in infos})
    detail = f"resolved to {addresses[0]}" + (f" (+{len(addresses) - 1} more)" if len(addresses) > 1 else "")
    return CheckStatus.OK, (time.monotonic() - start) * 1000, detail
