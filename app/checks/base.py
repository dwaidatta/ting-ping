import time

from app.checks.status import STATUS_INFO, CheckStatus
from app.models import CheckMethod, CheckResult, Target


async def run_check(target: Target) -> CheckResult:
    from app.checks import dns, http, ping, tcp

    dispatch = {
        CheckMethod.PING: ping.run_ping_check,
        CheckMethod.TCP: tcp.run_tcp_check,
        CheckMethod.HTTP: http.run_http_check,
        CheckMethod.DNS: dns.run_dns_check,
    }
    fn = dispatch[target.method]

    try:
        status, latency_ms, detail = await fn(target)
    except Exception as exc:
        # Anything a check failed to classify still lands in the fixed vocabulary.
        status, latency_ms, detail = CheckStatus.GENERAL_FAILURE, None, str(exc).strip()

    return CheckResult(
        ts=time.time(),
        success=status == CheckStatus.OK,
        latency_ms=latency_ms,
        code=status.value,
        label=STATUS_INFO[status]["label"],
        detail=detail or STATUS_INFO[status]["label"],
    )
