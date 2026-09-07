import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional


class CheckMethod(str, Enum):
    PING = "ping"
    TCP = "tcp"
    HTTP = "http"
    DNS = "dns"


@dataclass
class Target:
    id: str
    name: str
    host: str
    method: CheckMethod
    interval_s: int
    enabled: bool = True
    tcp_port: Optional[int] = None
    http_path: Optional[str] = None
    http_scheme: Optional[str] = None
    # Where this monitor sits in the dashboard grid. Persisted so a drag-and-drop
    # reorder survives a restart; renumbered 0..n-1 on every save.
    position: int = 0

    def to_json(self) -> dict:
        d = asdict(self)
        d["method"] = self.method.value if isinstance(self.method, CheckMethod) else self.method
        return d

    @staticmethod
    def from_json(d: dict) -> "Target":
        d = dict(d)
        d["method"] = CheckMethod(d["method"])
        # Targets written before ordering existed carry no position; they keep
        # the order they appear in on disk (see storage.load_targets).
        d.setdefault("position", 0)
        return Target(**d)

    @staticmethod
    def new(name: str, host: str, method: str, interval_s: int, **kwargs) -> "Target":
        return Target(
            id=str(uuid.uuid4()),
            name=name,
            host=host,
            method=CheckMethod(method),
            interval_s=interval_s,
            **kwargs,
        )


@dataclass
class CheckResult:
    ts: float
    success: bool
    latency_ms: Optional[float]
    code: str        # one of app.checks.status.CheckStatus
    label: str       # human phrasing of that code, e.g. "request timed out"
    detail: str      # what the probe itself reported

    def to_json(self) -> dict:
        return {
            "ts": self.ts,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "code": self.code,
            "label": self.label,
            "detail": self.detail,
        }


class TargetState:
    """Runtime-only companion to a Target: its in-memory result ring buffer.

    Never persisted — this is the concrete mechanism behind "no history":
    results live only as long as the process does.
    """

    def __init__(self, buffer_size: int):
        self.buffer: "deque[CheckResult]" = deque(maxlen=buffer_size)

    def push(self, result: CheckResult) -> None:
        self.buffer.append(result)

    def uptime_ratio(self) -> Optional[float]:
        if not self.buffer:
            return None
        return sum(1 for r in self.buffer if r.success) / len(self.buffer)

    def last(self) -> Optional[CheckResult]:
        return self.buffer[-1] if self.buffer else None
