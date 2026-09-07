"""Development server: restarts on every change under app/.

Deliberately does NOT use uvicorn's own --reload. On Windows, uvicorn runs
the reloaded worker under asyncio's SelectorEventLoop instead of the default
ProactorEventLoop — and SelectorEventLoop cannot spawn subprocesses, which is
exactly how the ping check (and the network-discovery sweep) works. Under
uvicorn's reload that fails with `NotImplementedError` on every ping.

watchfiles.run_process sidesteps this by restarting `run.py` as a fresh OS
process on each change, so every restart gets a normal top-level event loop.
"""

import sys
from pathlib import Path

from watchfiles import run_process

BASE_DIR = Path(__file__).resolve().parent

if __name__ == "__main__":
    run_process(str(BASE_DIR / "app"), target=f"{sys.executable} run.py", target_type="command")
