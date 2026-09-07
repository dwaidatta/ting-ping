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


settings = Settings()
