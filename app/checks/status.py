"""The fixed vocabulary of check outcomes.

Every check returns one of these codes and nothing else, so the UI can label a
failure the way a network tool would ("request timed out", "destination host
unreachable") instead of dumping a raw exception string.
"""

import errno
import socket
from enum import Enum


class CheckStatus(str, Enum):
    OK = "ok"
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"
    TTL_EXPIRED = "ttl_expired"
    REFUSED = "refused"
    RESET = "reset"
    DNS_FAILURE = "dns_failure"
    NETWORK_DOWN = "network_down"
    TLS_ERROR = "tls_error"
    HTTP_ERROR = "http_error"
    PERMISSION_DENIED = "permission_denied"
    CONFIG_ERROR = "config_error"
    GENERAL_FAILURE = "general_failure"


#: label -> what it means, in the words a network tool would use.
STATUS_INFO: dict[str, dict[str, str]] = {
    CheckStatus.OK: {
        "label": "ok",
        "description": "The check completed and the target answered as expected.",
    },
    CheckStatus.TIMEOUT: {
        "label": "request timed out",
        "description": "No answer arrived before the deadline. The host may be down, overloaded, or silently dropping the probe.",
    },
    CheckStatus.UNREACHABLE: {
        "label": "destination unreachable",
        "description": "A router replied that it has no path to the host. The target is off the network or its subnet is not routed.",
    },
    CheckStatus.TTL_EXPIRED: {
        "label": "TTL expired in transit",
        "description": "The probe ran out of hops before arriving — usually a routing loop or a path that is too long.",
    },
    CheckStatus.REFUSED: {
        "label": "connection refused",
        "description": "The host is up and reachable but nothing is listening on that port, or a firewall rejected the connection outright.",
    },
    CheckStatus.RESET: {
        "label": "connection reset",
        "description": "The connection was accepted and then torn down by the peer or something in the path.",
    },
    CheckStatus.DNS_FAILURE: {
        "label": "name resolution failed",
        "description": "The hostname could not be resolved to an address. The target may be misspelled, or your DNS resolver is failing.",
    },
    CheckStatus.NETWORK_DOWN: {
        "label": "network unreachable",
        "description": "This machine has no usable route out — the local link or its default gateway is down.",
    },
    CheckStatus.TLS_ERROR: {
        "label": "TLS handshake failed",
        "description": "The connection opened but the certificate was rejected or the TLS negotiation failed. The service is up; its certificate is not trusted.",
    },
    CheckStatus.HTTP_ERROR: {
        "label": "HTTP error response",
        "description": "The server answered with an error status (4xx or 5xx). The host is reachable but the endpoint is not healthy.",
    },
    CheckStatus.PERMISSION_DENIED: {
        "label": "permission denied",
        "description": "The operating system blocked the probe. Raw ICMP in particular often needs elevated privileges.",
    },
    CheckStatus.CONFIG_ERROR: {
        "label": "misconfigured",
        "description": "The monitor itself is set up wrong — a missing port, or a tool this machine does not have.",
    },
    CheckStatus.GENERAL_FAILURE: {
        "label": "general failure",
        "description": "The probe failed for a reason the network stack did not classify. Often a driver, adapter, or firewall issue on this machine.",
    },
}


def status_catalog() -> list[dict]:
    """Serialisable form of the vocabulary, handed to the UI at startup."""
    return [{"code": code.value, **info} for code, info in STATUS_INFO.items()]


def classify_oserror(exc: BaseException) -> CheckStatus:
    """Map a socket-level failure onto the fixed vocabulary."""
    if isinstance(exc, socket.gaierror):
        return CheckStatus.DNS_FAILURE
    if isinstance(exc, ConnectionRefusedError):
        return CheckStatus.REFUSED
    if isinstance(exc, ConnectionResetError):
        return CheckStatus.RESET
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return CheckStatus.TIMEOUT
    if isinstance(exc, PermissionError):
        return CheckStatus.PERMISSION_DENIED

    code = getattr(exc, "errno", None)
    if code in (errno.EHOSTUNREACH, errno.EHOSTDOWN):
        return CheckStatus.UNREACHABLE
    if code in (errno.ENETUNREACH, errno.ENETDOWN, errno.ENETRESET):
        return CheckStatus.NETWORK_DOWN
    if code == errno.ECONNREFUSED:
        return CheckStatus.REFUSED
    if code == errno.ECONNRESET:
        return CheckStatus.RESET
    if code in (errno.ETIMEDOUT,):
        return CheckStatus.TIMEOUT
    if code in (errno.EACCES, errno.EPERM):
        return CheckStatus.PERMISSION_DENIED

    return CheckStatus.GENERAL_FAILURE
