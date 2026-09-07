import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _path(env_var: str, default: Path) -> Path:
    raw = os.getenv(env_var)
    return Path(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("TP_HOST", "127.0.0.1")
    port: int = int(os.getenv("TP_PORT", "8420"))

    targets_file: Path = _path("TP_TARGETS_FILE", BASE_DIR / "data" / "targets.json")
    static_dir: Path = _path("TP_STATIC_DIR", BASE_DIR / "static")

    buffer_size: int = int(os.getenv("TP_BUFFER_SIZE", "60"))
    interval_min_s: int = int(os.getenv("TP_INTERVAL_MIN_S", "1"))
    interval_max_s: int = int(os.getenv("TP_INTERVAL_MAX_S", "60"))
    default_interval_s: int = int(os.getenv("TP_DEFAULT_INTERVAL_S", "5"))

    check_timeout_s: float = float(os.getenv("TP_CHECK_TIMEOUT_S", "3.0"))
    ping_timeout_s: float = float(os.getenv("TP_PING_TIMEOUT_S", "2.0"))
    http_timeout_s: float = float(os.getenv("TP_HTTP_TIMEOUT_S", "5.0"))
    tcp_timeout_s: float = float(os.getenv("TP_TCP_TIMEOUT_S", "3.0"))
    dns_timeout_s: float = float(os.getenv("TP_DNS_TIMEOUT_S", "3.0"))

    default_http_scheme: str = os.getenv("TP_DEFAULT_HTTP_SCHEME", "https")
    log_level: str = os.getenv("TP_LOG_LEVEL", "INFO")

    # Device-status probes.
    dns_probe_host: str = os.getenv("TP_DNS_PROBE_HOST", "example.com")
    gateway_probe_port: int = int(os.getenv("TP_GATEWAY_PROBE_PORT", "80"))
    internet_probe_host: str = os.getenv("TP_INTERNET_PROBE_HOST", "1.1.1.1")
    internet_probe_port: int = int(os.getenv("TP_INTERNET_PROBE_PORT", "443"))

    # The only outbound call this app makes on its own behalf. Set to 0 to keep
    # every request inside your own network.
    public_ip_lookup: bool = os.getenv("TP_PUBLIC_IP_LOOKUP", "1").strip().lower() not in ("0", "false", "no")
    public_ip_url: str = os.getenv("TP_PUBLIC_IP_URL", "https://ipinfo.io/json")
    public_ip_timeout_s: float = float(os.getenv("TP_PUBLIC_IP_TIMEOUT_S", "4.0"))

    # Network discovery: subnet sweep + port scan, both triggered by hand from
    # the discovery page. The "warn" thresholds are soft — crossing them just
    # makes the page ask the user to confirm before a click can pin the server
    # for minutes — while the "hard" caps are true ceilings nothing can bypass,
    # since concurrency below, not the cap itself, is what bounds how many
    # sockets are open at once.
    discovery_warn_hosts: int = int(os.getenv("TP_DISCOVERY_WARN_HOSTS", "1024"))
    discovery_hard_max_hosts: int = int(os.getenv("TP_DISCOVERY_HARD_MAX_HOSTS", "65536"))
    discovery_sweep_concurrency: int = int(os.getenv("TP_DISCOVERY_SWEEP_CONCURRENCY", "64"))
    discovery_warn_ports: int = int(os.getenv("TP_DISCOVERY_WARN_PORTS", "1024"))
    discovery_max_ports: int = int(os.getenv("TP_DISCOVERY_MAX_PORTS", "65535"))
    discovery_port_concurrency: int = int(os.getenv("TP_DISCOVERY_PORT_CONCURRENCY", "300"))
    port_scan_timeout_s: float = float(os.getenv("TP_PORT_SCAN_TIMEOUT_S", "3.0"))

    # Traceroute: shells out to the OS's own tracert/traceroute, streamed hop
    # by hop. "hard" is a true ceiling on how many hops the UI can ask for.
    traceroute_default_max_hops: int = int(os.getenv("TP_TRACEROUTE_MAX_HOPS", "30"))
    traceroute_hard_max_hops: int = int(os.getenv("TP_TRACEROUTE_HARD_MAX_HOPS", "64"))
    traceroute_hop_timeout_s: float = float(os.getenv("TP_TRACEROUTE_HOP_TIMEOUT_S", "2.0"))

    # Speed test: latency/jitter, download and upload throughput. Two
    # providers are supported — Cloudflare's public speed-test endpoints (the
    # same backend speed.cloudflare.com's own page hits from the browser) and
    # M-Lab's NDT7 (a nonprofit internet-measurement consortium's public,
    # documented test, discovered via their "locate" API) — so one CDN's
    # peering doesn't singlehandedly decide what the tool reports. No account
    # or API key needed for either.
    speedtest_url: str = os.getenv("TP_SPEEDTEST_URL", "https://speed.cloudflare.com")
    speedtest_download_bytes: int = int(os.getenv("TP_SPEEDTEST_DOWNLOAD_BYTES", str(64_000_000)))
    speedtest_upload_bytes: int = int(os.getenv("TP_SPEEDTEST_UPLOAD_BYTES", str(32_000_000)))
    # A single TCP stream rarely fills a fast, low-latency link on its own
    # (slow-start and the bandwidth-delay product cap it well below the real
    # capacity) — spreading the transfer across several concurrent
    # connections, the way every mainstream speed-test does, is the
    # difference between reporting a fraction of a link's real speed and
    # reporting something close to it. Applies to both providers.
    speedtest_download_connections: int = int(os.getenv("TP_SPEEDTEST_DOWNLOAD_CONNECTIONS", "8"))
    speedtest_upload_connections: int = int(os.getenv("TP_SPEEDTEST_UPLOAD_CONNECTIONS", "6"))
    speedtest_ping_samples: int = int(os.getenv("TP_SPEEDTEST_PING_SAMPLES", "10"))
    speedtest_timeout_s: float = float(os.getenv("TP_SPEEDTEST_TIMEOUT_S", "30.0"))

    # NDT7 (M-Lab): fixed-duration test per direction, per the protocol spec.
    # The upload message size is capped well below NDT7's own 1 MiB ceiling —
    # a single in-flight websocket send blocks until the transport accepts
    # it, and on a slow link a full-size message can overrun the deadline by
    # seconds because nothing can interrupt a send already in progress.
    speedtest_ndt7_locate_url: str = os.getenv(
        "TP_SPEEDTEST_NDT7_LOCATE_URL", "https://locate.measurementlab.net/v2/nearest/ndt/ndt7"
    )
    speedtest_ndt7_duration_s: float = float(os.getenv("TP_SPEEDTEST_NDT7_DURATION_S", "10.0"))
    speedtest_ndt7_max_msg_bytes: int = int(os.getenv("TP_SPEEDTEST_NDT7_MAX_MSG_BYTES", str(256 * 1024)))
    # A message send already in flight can't be interrupted, so the deadline
    # above is a soft target — this is the hard cap on how much longer a
    # stalled connection gets before it's cancelled outright.
    speedtest_ndt7_overrun_grace_s: float = float(os.getenv("TP_SPEEDTEST_NDT7_OVERRUN_GRACE_S", "3.0"))


settings = Settings()
