import ssl
import time

import httpx

from app.checks.status import CheckStatus, classify_oserror
from app.config import settings

_client: httpx.AsyncClient | None = None


def init_client() -> None:
    global _client
    _client = httpx.AsyncClient(follow_redirects=True, timeout=settings.http_timeout_s)


def get_client() -> httpx.AsyncClient | None:
    """Shared client, also used for the outbound public-IP lookup."""
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _unwrap(exc: BaseException):
    """Yield exc and everything beneath it, in order of increasing specificity.

    httpx wraps httpcore wraps the socket error; the inner links are joined by
    __context__ rather than __cause__, and anyio collapses several failed
    connection attempts into an ExceptionGroup. Follow all three or a refused
    connection reads as a generic error.
    """
    seen: set[int] = set()

    def walk(node: BaseException | None):
        while node is not None and id(node) not in seen:
            seen.add(id(node))
            yield node
            for sub in getattr(node, "exceptions", ()) or ():
                yield from walk(sub)
            node = node.__cause__ or node.__context__

    yield from walk(exc)


def _classify_transport_error(exc: Exception) -> tuple[CheckStatus, str]:
    fallback: tuple[CheckStatus, str] | None = None

    for node in _unwrap(exc):
        if isinstance(node, ssl.SSLError):
            return CheckStatus.TLS_ERROR, (getattr(node, "reason", None) or str(node)).strip()
        if isinstance(node, OSError):
            status = classify_oserror(node)
            detail = (getattr(node, "strerror", None) or str(node)).strip()
            if status != CheckStatus.GENERAL_FAILURE:
                return status, detail
            # An OSError carrying no errno (anyio's "all attempts failed") is only
            # a summary — keep looking for the specific failure underneath it.
            fallback = fallback or (status, detail)

    if fallback:
        return fallback

    text = str(exc).strip() or exc.__class__.__name__
    if "certificate" in text.lower() or "ssl" in text.lower():
        return CheckStatus.TLS_ERROR, text
    return CheckStatus.GENERAL_FAILURE, text


async def run_http_check(target) -> tuple[CheckStatus, float | None, str]:
    scheme = target.http_scheme or settings.default_http_scheme
    path = target.http_path or "/"
    url = f"{scheme}://{target.host}{path}"

    if _client is None:
        return CheckStatus.CONFIG_ERROR, None, "HTTP client is not initialised"

    start = time.monotonic()
    try:
        resp = await _client.get(url, timeout=settings.http_timeout_s)
    except httpx.TimeoutException:
        return CheckStatus.TIMEOUT, None, f"no response within {settings.http_timeout_s:g}s"
    except httpx.TooManyRedirects:
        return CheckStatus.HTTP_ERROR, None, "redirect loop"
    except httpx.HTTPError as exc:
        status, detail = _classify_transport_error(exc)
        return status, None, detail

    latency = (time.monotonic() - start) * 1000
    if resp.status_code >= 400:
        return CheckStatus.HTTP_ERROR, latency, f"HTTP {resp.status_code} {resp.reason_phrase}".strip()
    return CheckStatus.OK, latency, f"HTTP {resp.status_code} {resp.reason_phrase}".strip()
