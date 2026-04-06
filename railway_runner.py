"""Run the dashboard server and scheduler in one container.

This keeps SQLite, tokens, outputs, and queue state in one service, which is
safer on platforms where multiple services do not share the same local disk.
"""

from __future__ import annotations

import signal
import subprocess
import sys
import time


def _start_process(command: list[str]) -> subprocess.Popen:
    return subprocess.Popen(command)


def main() -> int:
    scheduler = _start_process([sys.executable, "scheduler.py"])
    server = _start_process([sys.executable, "server.py"])
    children = [scheduler, server]

    def _shutdown(signum, _frame) -> None:
        print(f"Received signal {signum}; shutting down child processes...")
        for child in children:
            if child.poll() is None:
                child.terminate()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        while True:
            scheduler_code = scheduler.poll()
            server_code = server.poll()

            if scheduler_code is not None or server_code is not None:
                for child in children:
                    if child.poll() is None:
                        child.terminate()
                time.sleep(2)
                for child in children:
                    if child.poll() is None:
                        child.kill()
                return scheduler_code or server_code or 0

            time.sleep(2)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()


if __name__ == "__main__":
    raise SystemExit(main())