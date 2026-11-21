"""Не зависит от веб-фреймворка: безопасность и фоновые задачи сервера, чтобы их можно было тестировать."""
from __future__ import annotations

import os
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

ALLOWED_VIDEO = {".mp4", ".mov", ".m4v", ".webm"}
_style_lock = threading.Lock()


class UploadError(ValueError):
    pass


def check_token(provided: str | None, expected: str) -> bool:
    return bool(provided and expected) and secrets.compare_digest(provided.encode(), expected.encode())


def save_upload(src, dest_dir: Path, filename: str | None, max_bytes: int, allowed=ALLOWED_VIDEO) -> Path:
    """Сохраняет загрузку кусками с жёстким лимитом размера и белым списком расширений."""
    ext = Path(filename or "").suffix.lower()
    if ext not in allowed:
        raise UploadError(f"Неподдерживаемый формат {ext or '(нет)'}; разрешено: {', '.join(sorted(allowed))}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(suffix=ext, dir=dest_dir)
    path, total = Path(name), 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise UploadError(f"Файл больше лимита {max_bytes // (1 << 20)} МБ")
                out.write(chunk)
        if total == 0:
            raise UploadError("Пустой файл")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def append_style(path: Path, phrase: str, max_len: int = 300) -> bool:
    """Одна строка, без переводов строк и комментариев; дубликаты не добавляются."""
    clean = " ".join((phrase or "").split())
    if not clean or clean.startswith("#"):
        raise ValueError("Пустая или недопустимая фраза")
    if len(clean) > max_len:
        raise ValueError(f"Фраза длиннее {max_len} символов")
    with _style_lock:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if clean in (x.strip() for x in existing.splitlines()):
            return False
        with path.open("a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(clean + "\n")
    return True


class ResearchJob:
    """Один фоновый поиск за раз. Телефон опрашивает статус вместо долгого HTTP-запроса."""

    def __init__(self):
        self._lock = threading.Lock()
        self._status = {"running": False, "started_at": None, "finished_at": None, "result": None, "error": None}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def start(self, fn) -> bool:
        with self._lock:
            if self._status["running"]:
                return False
            self._status.update(running=True, started_at=self._now(), finished_at=None, result=None, error=None)
        threading.Thread(target=self._run, args=(fn,), daemon=True).start()
        return True

    def _run(self, fn) -> None:
        result = error = None
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - любой сбой должен попасть в статус, а не убить поток молча
            error = f"{type(exc).__name__}: {exc}"[:300]
        with self._lock:
            self._status.update(running=False, finished_at=self._now(), result=result, error=error)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._status)
