from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from types import TracebackType
from typing import Any

if os.name == "nt":
    import msvcrt
else:
    import fcntl


DEFAULT_TAX_BROWSER_LOCK = Path("runtime") / "tax_browser.lock"


class ProcessLock:
    """Small cross-process lock backed by an OS file lock."""

    def __init__(
        self,
        path: str | Path,
        timeout: int | float | None = 3600,
        poll_interval: float = 1.0,
        owner: dict[str, Any] | None = None,
    ) -> None:
        self.path = Path(path)
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.owner = owner or {}
        self._fh = None
        self.acquired = False

    def acquire(self) -> "ProcessLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a+", encoding="utf-8")
        self._ensure_lock_byte()
        deadline = None if self.timeout is None else time.time() + self.timeout
        while True:
            try:
                self._lock_nonblocking()
                self.acquired = True
                self._write_owner()
                return self
            except OSError as exc:
                if deadline is not None and time.time() >= deadline:
                    current_owner = self.read_owner()
                    self.close_file()
                    raise TimeoutError(
                        f"Timed out waiting for process lock: {self.path}; owner={current_owner}"
                    ) from exc
                time.sleep(self.poll_interval)

    def release(self) -> None:
        if not self._fh:
            return
        try:
            if self.acquired:
                self._fh.seek(0)
                self._fh.truncate()
                self._fh.write(json.dumps({"releasedBy": os.getpid(), "releasedAt": time.time()}))
                self._fh.flush()
                self._fh.seek(0)
                self._unlock()
        finally:
            self.acquired = False
            self.close_file()

    def read_owner(self) -> dict[str, Any] | str:
        try:
            text = self.path.read_text(encoding="utf-8").strip()
        except OSError:
            return {}
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def close_file(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def _ensure_lock_byte(self) -> None:
        assert self._fh is not None
        self._fh.seek(0, os.SEEK_END)
        if self._fh.tell() == 0:
            self._fh.write(" ")
            self._fh.flush()
        self._fh.seek(0)

    def _lock_nonblocking(self) -> None:
        assert self._fh is not None
        self._fh.seek(0)
        if os.name == "nt":
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(self) -> None:
        assert self._fh is not None
        self._fh.seek(0)
        if os.name == "nt":
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)

    def _write_owner(self) -> None:
        assert self._fh is not None
        payload = {
            "pid": os.getpid(),
            "argv": sys.argv,
            "acquiredAt": time.time(),
            **self.owner,
        }
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(json.dumps(payload, ensure_ascii=False, indent=2))
        self._fh.flush()
        self._fh.seek(0)

    def __enter__(self) -> "ProcessLock":
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
