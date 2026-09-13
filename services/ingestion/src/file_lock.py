"""Small cross-platform inter-process file mutex.

The lock is held by the operating system for the lifetime of the open handle.
The on-disk file is persistent metadata, so a crashed process cannot leave a
false live lock behind and acquisition does not use an exists-then-write race.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LockUnavailable(RuntimeError):
    pass


def _owner_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.owner.json")


def _metadata_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "pid": os.getpid(),
        "token": uuid.uuid4().hex,
        "acquiredAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **metadata,
    }


def read_lock_metadata(path: Path) -> dict[str, Any]:
    try:
        metadata_path = _owner_path(path)
        raw = metadata_path.read_bytes() if metadata_path.is_file() else path.read_bytes()
        if raw.startswith(b"\0"):
            raw = raw[1:]
        return json.loads(raw.decode("utf-8")) if raw.strip() else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


class FileMutex:
    def __init__(self, path: Path, metadata: dict[str, Any] | None = None) -> None:
        self.path = path
        self.metadata = metadata or {}
        self._stream = None
        self._locked = False

    def __enter__(self) -> "FileMutex":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+b")
        self._stream = stream
        try:
            if sys.platform == "win32":
                import msvcrt

                stream.seek(0, os.SEEK_END)
                if stream.tell() == 0:
                    stream.write(b"\0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            stream.close()
            self._stream = None
            raise LockUnavailable(f"lock is already held: {self.path}") from exc

        self._locked = True
        metadata = _metadata_payload(self.metadata)
        owner_path = _owner_path(self.path)
        try:
            # This file is diagnostic metadata rather than the mutex itself.  The
            # OS lock serialises writers, and readers already tolerate a partial
            # JSON document.  Writing it in place also works on Windows volumes
            # that reject replacing an existing file while a sibling lock is open.
            owner_path.write_text(
                json.dumps(metadata, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        stream = self._stream
        if stream is None:
            return
        try:
            if self._locked:
                if sys.platform == "win32":
                    import msvcrt

                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            self._locked = False
            stream.close()
            self._stream = None


def lock_is_held(path: Path) -> bool:
    try:
        with FileMutex(path, {"probe": True}):
            return False
    except LockUnavailable:
        return True
