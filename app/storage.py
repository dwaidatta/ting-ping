import json
import threading

from app.config import settings
from app.models import Target

_lock = threading.Lock()


def load_targets() -> list[Target]:
    """Targets in dashboard order.

    Sorting is stable, so a file written before ordering existed — every target
    at position 0 — simply keeps the order it was stored in.
    """
    if not settings.targets_file.exists():
        return []
    with open(settings.targets_file, "r", encoding="utf-8") as f:
        raw = json.load(f)
    targets = [Target.from_json(t) for t in raw]
    return sorted(targets, key=lambda t: t.position)


def save_targets(targets: list[Target]) -> None:
    """Persist targets in the order given, renumbering positions to match.

    The list order is the dashboard order, so the caller never has to keep
    `position` in step by hand.
    """
    settings.targets_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = settings.targets_file.with_suffix(".json.tmp")
    with _lock:
        for i, target in enumerate(targets):
            target.position = i
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump([t.to_json() for t in targets], f, indent=2)
        tmp.replace(settings.targets_file)
