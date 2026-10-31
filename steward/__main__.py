"""Run the admin UI and the API together."""

import signal
import subprocess
import sys

from steward.settings import get_settings

_MODULES = ("steward.admin", "steward.api")


def main() -> None:
    """Start the admin and API processes and exit when one of them stops."""
    settings = get_settings()
    print(f"admin  http://{settings.admin_host}:{settings.admin_port}", flush=True)
    print(f"api    http://{settings.api_host}:{settings.api_port}", flush=True)
    processes = [subprocess.Popen([sys.executable, "-m", module], start_new_session=True) for module in _MODULES]
    _wait(processes)


def _wait(processes: list[subprocess.Popen[bytes]]) -> None:
    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True
        _terminate(processes)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while not stopping:
            alive = [process for process in processes if process.poll() is None]
            if len(alive) != len(processes):
                break
            try:
                alive[0].wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                continue
    finally:
        _terminate(processes)
        for process in processes:
            process.wait()
    raise SystemExit(_exit_code(processes))


def _terminate(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()


def _exit_code(processes: list[subprocess.Popen[bytes]]) -> int:
    for process in processes:
        code = process.returncode
        if code not in (0, -signal.SIGTERM, -signal.SIGINT):
            return code if code is not None and code > 0 else 1
    return 0


if __name__ == "__main__":
    main()
