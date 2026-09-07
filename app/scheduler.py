import asyncio
import logging
from typing import Awaitable, Callable

from app.checks.base import run_check
from app.config import settings
from app.models import Target, TargetState

logger = logging.getLogger("tingping.scheduler")

BroadcastFn = Callable[[dict], Awaitable[None]]


class TargetScheduler:
    def __init__(self, broadcast_fn: BroadcastFn):
        self._targets: dict[str, Target] = {}
        self._states: dict[str, TargetState] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._broadcast = broadcast_fn

    def snapshot(self) -> dict:
        return {
            tid: {
                "target": t.to_json(),
                "buffer": [r.to_json() for r in self._states[tid].buffer],
                "uptime_ratio": self._states[tid].uptime_ratio(),
            }
            for tid, t in self._targets.items()
        }

    def targets(self) -> list[Target]:
        return list(self._targets.values())

    def load_initial(self, targets: list[Target]) -> None:
        for t in targets:
            self._register(t)

    def _register(self, target: Target) -> None:
        self._targets[target.id] = target
        self._states.setdefault(target.id, TargetState(settings.buffer_size))
        if target.enabled:
            self._start_task(target.id)

    def add(self, target: Target) -> None:
        self._register(target)

    def remove(self, target_id: str) -> None:
        self._stop_task(target_id)
        self._targets.pop(target_id, None)
        self._states.pop(target_id, None)

    def reorder(self, ordered_ids: list[str]) -> None:
        """Rebuild the target map in the given order.

        `_targets` is an ordinary dict, so its insertion order is what
        `targets()` and `snapshot()` hand out — reordering is purely a matter of
        rebuilding it. Ids not mentioned keep their relative order at the end,
        which is what happens when a monitor is added by another client while
        someone is mid-drag. Running check loops are untouched.
        """
        seen = set()
        reordered: dict[str, Target] = {}
        for tid in ordered_ids:
            target = self._targets.get(tid)
            if target is None or tid in seen:
                continue
            seen.add(tid)
            reordered[tid] = target
        for tid, target in self._targets.items():
            if tid not in seen:
                reordered[tid] = target

        self._targets = reordered
        for i, target in enumerate(self._targets.values()):
            target.position = i

    def update(self, target: Target) -> None:
        self._stop_task(target.id)
        self._targets[target.id] = target
        self._states.setdefault(target.id, TargetState(settings.buffer_size))
        if target.enabled:
            self._start_task(target.id)

    def _start_task(self, target_id: str) -> None:
        if target_id in self._tasks:
            return
        self._tasks[target_id] = asyncio.create_task(
            self._run_loop(target_id), name=f"check-{target_id}"
        )

    def _stop_task(self, target_id: str) -> None:
        task = self._tasks.pop(target_id, None)
        if task:
            task.cancel()

    async def _run_loop(self, target_id: str) -> None:
        try:
            while True:
                target = self._targets.get(target_id)
                if target is None:
                    return
                result = await run_check(target)
                state = self._states.get(target_id)
                if state is None:
                    return
                state.push(result)
                await self._broadcast(
                    {
                        "type": "check_result",
                        "target_id": target_id,
                        "result": result.to_json(),
                        "uptime_ratio": state.uptime_ratio(),
                    }
                )
                await asyncio.sleep(target.interval_s)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("check loop for %s crashed", target_id)

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for tid in list(self._tasks):
            self._stop_task(tid)
        await asyncio.gather(*tasks, return_exceptions=True)
