"""Ad-hoc internet speed test: latency/jitter, then download and upload
throughput. Two independent providers are supported so the result isn't
singlehandedly decided by one CDN's peering:

- "cloudflare" — Cloudflare's public speed-test endpoints (the same backend
  speed.cloudflare.com's own page hits from the browser).
- "ndt7" — M-Lab's NDT7 protocol, a nonprofit internet-measurement
  consortium's public, documented test. The nearest server is found via
  their "locate" API, then the download/upload test runs over a websocket
  per the NDT7 spec.

Both stream the same event shape — phase markers, progress events, one
result event per stage, a final `done` (or `error`) — so the frontend
doesn't need to know which provider is running. Nothing here is scheduled
or persisted, the same as traceroute and discovery."""

import asyncio
import os
import time
from urllib.parse import urlparse

import httpx
import websockets

from app.checks.http import get_client
from app.config import settings

PROVIDERS = ("cloudflare", "ndt7")
DEFAULT_PROVIDER = "cloudflare"

# Progress events fire at most this often, so a fast connection doesn't spam
# the client with an event every few milliseconds.
_PROGRESS_INTERVAL_S = 0.15
_CHUNK_SIZE = 65536

_NDT7_SUBPROTOCOL = "net.measurementlab.ndt.v7"


# ── shared: latency/jitter via raw TCP connect time ──────────────────────
#
# A plain TCP handshake (one round trip, no TLS/HTTP layered on top) is a
# cleaner "ping" than timing an HTTPS request — it isn't skewed by TLS
# renegotiation or connection-reuse quirks, and it works the same way
# against any host:port, so both providers share this one implementation.


async def _tcp_ping(host: str, port: int, samples: int) -> dict | None:
    results: list[float] = []
    for _ in range(samples):
        start = time.monotonic()
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5.0)
        except (OSError, asyncio.TimeoutError):
            continue
        results.append((time.monotonic() - start) * 1000)
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass

    if not results:
        return None
    avg = sum(results) / len(results)
    jitter = sum(abs(r - avg) for r in results) / len(results) if len(results) > 1 else 0.0
    return {"ping_ms": avg, "jitter_ms": jitter, "samples": len(results)}


# ── cloudflare ─────────────────────────────────────────────────────────


async def _cloudflare_download_connection(client: httpx.AsyncClient, chunk_bytes: int, progress: list[int], index: int):
    async with client.stream(
        "GET", f"{settings.speedtest_url}/__down", params={"bytes": chunk_bytes}, timeout=settings.speedtest_timeout_s
    ) as resp:
        resp.raise_for_status()
        async for chunk in resp.aiter_bytes(_CHUNK_SIZE):
            progress[index] += len(chunk)


async def _cloudflare_download(client: httpx.AsyncClient, total_bytes: int):
    streams = max(1, settings.speedtest_download_connections)
    chunk_bytes = max(1, total_bytes // streams)
    actual_total = chunk_bytes * streams
    progress = [0] * streams

    start = time.monotonic()
    last_emit = start
    tasks = [
        asyncio.create_task(_cloudflare_download_connection(client, chunk_bytes, progress, i)) for i in range(streams)
    ]
    try:
        while not all(t.done() for t in tasks):
            await asyncio.sleep(_PROGRESS_INTERVAL_S)
            now = time.monotonic()
            if now - last_emit >= _PROGRESS_INTERVAL_S:
                last_emit = now
                yield {
                    "type": "download_progress",
                    "bytes": sum(progress),
                    "total": actual_total,
                    "elapsed_s": now - start,
                }
        for task in tasks:
            task.result()
    except BaseException:
        # Client aborted (GeneratorExit) or one connection failed — either
        # way, don't leave the rest running in the background.
        for task in tasks:
            task.cancel()
        raise

    elapsed = time.monotonic() - start
    received = sum(progress)
    mbps = (received * 8) / elapsed / 1_000_000 if elapsed > 0 else None
    yield {"type": "download", "mbps": mbps, "bytes": received, "elapsed_s": elapsed}


async def _cloudflare_upload_body(total_bytes: int, progress: list[int], index: int):
    """One randomly-filled chunk, repeated — the bytes only need to be
    incompressible and the right size, not actually random each time."""
    chunk = os.urandom(_CHUNK_SIZE)
    sent = 0
    while sent < total_bytes:
        piece = chunk if sent + _CHUNK_SIZE <= total_bytes else chunk[: total_bytes - sent]
        sent += len(piece)
        progress[index] = sent
        yield piece


async def _cloudflare_upload_connection(client: httpx.AsyncClient, chunk_bytes: int, progress: list[int], index: int):
    resp = await client.post(
        f"{settings.speedtest_url}/__up",
        content=_cloudflare_upload_body(chunk_bytes, progress, index),
        timeout=settings.speedtest_timeout_s,
    )
    resp.raise_for_status()


async def _cloudflare_upload(client: httpx.AsyncClient, total_bytes: int):
    streams = max(1, settings.speedtest_upload_connections)
    chunk_bytes = max(1, total_bytes // streams)
    actual_total = chunk_bytes * streams
    progress = [0] * streams

    start = time.monotonic()
    last_emit = start
    tasks = [asyncio.create_task(_cloudflare_upload_connection(client, chunk_bytes, progress, i)) for i in range(streams)]
    try:
        while not all(t.done() for t in tasks):
            await asyncio.sleep(_PROGRESS_INTERVAL_S)
            now = time.monotonic()
            if now - last_emit >= _PROGRESS_INTERVAL_S:
                last_emit = now
                yield {
                    "type": "upload_progress",
                    "bytes": sum(progress),
                    "total": actual_total,
                    "elapsed_s": now - start,
                }
        for task in tasks:
            task.result()
    except BaseException:
        for task in tasks:
            task.cancel()
        raise

    elapsed = time.monotonic() - start
    sent = sum(progress)
    mbps = (sent * 8) / elapsed / 1_000_000 if elapsed > 0 else None
    yield {"type": "upload", "mbps": mbps, "bytes": sent, "elapsed_s": elapsed}


async def _run_cloudflare(client: httpx.AsyncClient):
    host = urlparse(settings.speedtest_url).hostname or "speed.cloudflare.com"
    yield {"type": "server", "provider": "cloudflare", "host": host}

    yield {"type": "phase", "phase": "ping"}
    latency = await _tcp_ping(host, 443, settings.speedtest_ping_samples)
    if latency is None:
        yield {"type": "error", "message": f"could not reach {host} for a latency check"}
        return
    yield {"type": "ping", **latency}

    yield {"type": "phase", "phase": "download"}
    download_result = None
    async for event in _cloudflare_download(client, settings.speedtest_download_bytes):
        if event["type"] == "download":
            download_result = event
        yield event

    yield {"type": "phase", "phase": "upload"}
    upload_result = None
    async for event in _cloudflare_upload(client, settings.speedtest_upload_bytes):
        if event["type"] == "upload":
            upload_result = event
        yield event

    yield {
        "type": "done",
        "ping_ms": latency["ping_ms"],
        "jitter_ms": latency["jitter_ms"],
        "download_mbps": download_result["mbps"] if download_result else None,
        "upload_mbps": upload_result["mbps"] if upload_result else None,
    }


# ── ndt7 (m-lab) ───────────────────────────────────────────────────────


async def _ndt7_locate(client: httpx.AsyncClient) -> list[dict]:
    """Returns every candidate server M-Lab's locate API offers, ranked by
    its own preference. Several of these — especially community "autojoin"
    nodes — can be temporarily overloaded or unreachable, so the caller
    should be prepared to fall through the list rather than trust the first
    entry."""
    resp = await client.get(settings.speedtest_ndt7_locate_url, timeout=10.0)
    resp.raise_for_status()
    results = (resp.json() or {}).get("results") or []
    if not results:
        raise RuntimeError("no M-Lab NDT7 server is available near this location right now")
    return results


def _ndt7_candidate_urls(candidate: dict) -> tuple[str, str] | None:
    urls = candidate.get("urls") or {}
    download_url = urls.get("wss:///ndt/v7/download")
    upload_url = urls.get("wss:///ndt/v7/upload")
    if not download_url or not upload_url:
        return None
    return download_url, upload_url


async def _ndt7_connection(url: str, kind: str, progress: list[int], index: int, deadline: float):
    async with websockets.connect(url, subprotocols=[_NDT7_SUBPROTOCOL], open_timeout=10, max_size=None) as ws:
        if kind == "download":
            async for message in ws:
                if isinstance(message, (bytes, bytearray)):
                    progress[index] += len(message)
                if time.monotonic() >= deadline:
                    break
        else:
            buf = os.urandom(settings.speedtest_ndt7_max_msg_bytes)
            size = 8192
            while time.monotonic() < deadline:
                piece = buf[:size] if size < len(buf) else buf
                await ws.send(piece)
                progress[index] += len(piece)
                size = min(size * 2, settings.speedtest_ndt7_max_msg_bytes)


async def _ndt7_transfer(url: str, kind: str, connections: int):
    """Runs `connections` concurrent NDT7 websocket streams against `url` for
    the configured duration, yielding progress events and a final result —
    same event shape as the Cloudflare transfer, except progress is reported
    against elapsed/duration (NDT7 is time-bounded, not byte-bounded)."""
    progress = [0] * max(1, connections)
    start = time.monotonic()
    deadline = start + settings.speedtest_ndt7_duration_s
    hard_deadline = deadline + settings.speedtest_ndt7_overrun_grace_s
    last_emit = start

    tasks = [asyncio.create_task(_ndt7_connection(url, kind, progress, i, deadline)) for i in range(len(progress))]
    try:
        while not all(t.done() for t in tasks):
            await asyncio.sleep(_PROGRESS_INTERVAL_S)
            now = time.monotonic()
            if now >= hard_deadline:
                # A send already in flight can't be interrupted — this
                # connection is past even its grace period, so cut it loose
                # rather than let one stalled stream hold up the whole test.
                for task in tasks:
                    if not task.done():
                        task.cancel()
                break
            if now - last_emit >= _PROGRESS_INTERVAL_S:
                last_emit = now
                yield {
                    "type": f"{kind}_progress",
                    "bytes": sum(progress),
                    "elapsed_s": now - start,
                    "duration_s": settings.speedtest_ndt7_duration_s,
                }
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                raise result
    except BaseException:
        for task in tasks:
            task.cancel()
        raise

    elapsed = time.monotonic() - start
    total = sum(progress)
    mbps = (total * 8) / elapsed / 1_000_000 if elapsed > 0 else None
    yield {"type": kind, "mbps": mbps, "bytes": total, "elapsed_s": elapsed}


_NDT7_MAX_CANDIDATES = 3


async def _run_ndt7(client: httpx.AsyncClient):
    try:
        candidates = await _ndt7_locate(client)
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        yield {"type": "error", "message": f"could not reach M-Lab: {exc}"}
        return

    last_error: str | None = None
    for candidate in candidates[:_NDT7_MAX_CANDIDATES]:
        urls = _ndt7_candidate_urls(candidate)
        if urls is None:
            continue
        download_url, upload_url = urls
        host = urlparse(download_url).hostname or "measurement-lab.org"
        location = candidate.get("location") or {}
        where = ", ".join(v for v in (location.get("city"), location.get("country")) if v)
        yield {"type": "server", "provider": "ndt7", "host": host, "location": where or None}

        yield {"type": "phase", "phase": "ping"}
        latency = await _tcp_ping(host, 443, settings.speedtest_ping_samples)
        if latency is None:
            last_error = f"could not reach {host} for a latency check"
            continue
        yield {"type": "ping", **latency}

        try:
            yield {"type": "phase", "phase": "download"}
            download_result = None
            async for event in _ndt7_transfer(download_url, "download", settings.speedtest_download_connections):
                if event["type"] == "download":
                    download_result = event
                yield event

            yield {"type": "phase", "phase": "upload"}
            upload_result = None
            async for event in _ndt7_transfer(upload_url, "upload", settings.speedtest_upload_connections):
                if event["type"] == "upload":
                    upload_result = event
                yield event
        except (websockets.exceptions.WebSocketException, OSError, asyncio.TimeoutError) as exc:
            # This candidate (often a community "autojoin" node) is
            # unreachable or dropped mid-transfer — try the next one M-Lab
            # offered rather than fail the whole test on one flaky server.
            last_error = f"{host}: {type(exc).__name__}: {exc}"
            continue

        yield {
            "type": "done",
            "ping_ms": latency["ping_ms"],
            "jitter_ms": latency["jitter_ms"],
            "download_mbps": download_result["mbps"] if download_result else None,
            "upload_mbps": upload_result["mbps"] if upload_result else None,
        }
        return

    yield {"type": "error", "message": f"no working NDT7 server was found ({last_error or 'no candidates offered'})"}


_RUNNERS = {"cloudflare": _run_cloudflare, "ndt7": _run_ndt7}


async def speedtest_stream(provider: str = DEFAULT_PROVIDER):
    """Yields `{"type": "server", ...}`, phase markers, progress events,
    result events, and a final `done` (or `error`) event. Same early-stop
    handling as traceroute/discovery: if the caller stops consuming early,
    in-flight requests are cancelled instead of finishing in the background."""
    if provider not in _RUNNERS:
        yield {"type": "error", "message": f"unknown speed-test provider '{provider}'"}
        return

    client = get_client()
    if client is None:
        yield {"type": "error", "message": "HTTP client is not initialised"}
        return

    try:
        async for event in _RUNNERS[provider](client):
            yield event
    except httpx.HTTPError as exc:
        yield {"type": "error", "message": f"speed test failed: {type(exc).__name__}: {exc}"}
