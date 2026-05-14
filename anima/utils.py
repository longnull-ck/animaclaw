"""
Anima — Utilities
Atomic file writes and process locking.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger("anima.utils")


# ── Atomic File Write ─────────────────────────────────────────

def atomic_write_text(path: Path | str, content: str, encoding: str = "utf-8") -> None:
    """
    Write content to file atomically.
    Uses write-to-temp + rename to prevent corruption on crash/power loss.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory (ensures same filesystem for rename)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.stem}_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        # Atomic rename (on POSIX; on Windows this replaces if exists on Python 3.3+)
        os.replace(tmp_path, str(path))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path | str, data: dict | list, encoding: str = "utf-8") -> None:
    """Write JSON data atomically."""
    content = json.dumps(data, ensure_ascii=False, indent=2)
    atomic_write_text(path, content, encoding=encoding)


# ── Process Lock ──────────────────────────────────────────────

class ProcessLock:
    """
    Simple file-based process lock to prevent multiple instances.
    Uses PID file with stale lock detection.
    """

    def __init__(self, lock_file: Path | str):
        self._lock_file = Path(lock_file)
        self._lock_file.parent.mkdir(parents=True, exist_ok=True)

    def acquire(self) -> bool:
        """
        Try to acquire the lock.
        Returns True if acquired, False if another instance is running.
        """
        if self._lock_file.exists():
            try:
                stored_pid = int(self._lock_file.read_text().strip())
                if self._is_pid_alive(stored_pid):
                    return False
                else:
                    # Stale lock, remove it
                    logger.info(f"Removing stale lock (PID {stored_pid} not running)")
                    self._lock_file.unlink()
            except (ValueError, OSError):
                # Corrupt lock file, remove it
                self._lock_file.unlink(missing_ok=True)

        # Write our PID
        self._lock_file.write_text(str(os.getpid()))
        return True

    def release(self) -> None:
        """Release the lock."""
        try:
            if self._lock_file.exists():
                stored_pid = int(self._lock_file.read_text().strip())
                if stored_pid == os.getpid():
                    self._lock_file.unlink()
        except (ValueError, OSError):
            self._lock_file.unlink(missing_ok=True)

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """Check if a process with given PID is still running."""
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            except Exception:
                return False
        else:
            try:
                os.kill(pid, 0)
                return True
            except (OSError, ProcessLookupError):
                return False

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(
                "Another Anima instance is already running.\n"
                "Stop it first or delete the lock file: " + str(self._lock_file)
            )
        return self

    def __exit__(self, *args):
        self.release()
