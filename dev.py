import os
import subprocess
import sys
import time
from pathlib import Path


def iter_py_files(root: Path):
    for path in root.rglob("*.py"):
        if "/.venv/" in str(path):
            continue
        yield path


def snapshot_mtimes(root: Path) -> dict[str, float]:
    return {str(p): p.stat().st_mtime for p in iter_py_files(root)}


def run_app() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "main.py"], env=os.environ.copy())


def main() -> None:
    root = Path(__file__).resolve().parent
    mtimes = snapshot_mtimes(root)
    proc = run_app()
    try:
        while True:
            time.sleep(0.5)
            new_mtimes = snapshot_mtimes(root)
            if new_mtimes != mtimes:
                mtimes = new_mtimes
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                proc = run_app()
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.terminate()


if __name__ == "__main__":
    main()
