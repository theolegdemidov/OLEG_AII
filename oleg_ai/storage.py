from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos(
  video_id TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT NOT NULL, channel TEXT NOT NULL,
  published_at TEXT, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
  reported_at TEXT, views INTEGER NOT NULL, ratio REAL, payload_json TEXT NOT NULL,
  analysis_json TEXT);
CREATE TABLE IF NOT EXISTS snapshots(
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT NOT NULL, captured_at TEXT NOT NULL,
  views INTEGER NOT NULL, subscribers INTEGER, ratio REAL);
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, finished_at TEXT,
  status TEXT NOT NULL, reported_count INTEGER DEFAULT 0, error TEXT);
CREATE TABLE IF NOT EXISTS drafts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT NOT NULL, text TEXT NOT NULL,
  status TEXT NOT NULL, final_text TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS own_videos(
  url TEXT PRIMARY KEY, platform TEXT NOT NULL, published_at TEXT, views INTEGER,
  avg_view_pct REAL, likes INTEGER, comments INTEGER, saves INTEGER, imported_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS video_audits(
  id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL, hook_score REAL,
  report_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS content_queue(
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL,
  hashtags TEXT NOT NULL, media_url TEXT, platform TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft', external_url TEXT, error TEXT, created_at TEXT NOT NULL);
"""


class Store:
    """SQLite с общей блокировкой: сервер обслуживает запросы из нескольких потоков."""

    def __init__(self, path: Path | str):
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.executescript(SCHEMA)
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(videos)")}
            if "analysis_json" not in cols:  # миграция со старой версии БД
                self.conn.execute("ALTER TABLE videos ADD COLUMN analysis_json TEXT")
            self.conn.commit()

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _run(self, sql: str, params=()):
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def _all(self, sql: str, params=()):
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    # ---- найденные ролики -------------------------------------------------
    def record(self, item: dict) -> None:
        now = self.now()
        with self.lock:
            self.conn.execute(
                """INSERT INTO videos(video_id,url,title,channel,published_at,first_seen_at,last_seen_at,
                                      views,ratio,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(video_id) DO UPDATE SET last_seen_at=excluded.last_seen_at,
                     views=excluded.views, ratio=excluded.ratio, payload_json=excluded.payload_json""",
                (item["id"], item["url"], item["title"], item["channel"], item.get("published"),
                 now, now, item["views"], item.get("ratio"), json.dumps(item, ensure_ascii=False)))
            self.conn.execute(
                "INSERT INTO snapshots(video_id,captured_at,views,subscribers,ratio) VALUES(?,?,?,?,?)",
                (item["id"], now, item["views"], item.get("subs"), item.get("ratio")))
            self.conn.commit()

    def save_analysis(self, video_id: str, data: dict) -> None:
        self._run("UPDATE videos SET analysis_json=? WHERE video_id=?",
                  (json.dumps(data, ensure_ascii=False), video_id))

    def unanalyzed(self, limit: int) -> list[dict]:
        rows = self._all("SELECT payload_json FROM videos WHERE analysis_json IS NULL "
                         "ORDER BY ratio DESC, views DESC LIMIT ?", (limit,))
        return [json.loads(r[0]) for r in rows]

    def growth(self, video_id: str) -> dict | None:
        rows = self._all("SELECT captured_at, views FROM snapshots WHERE video_id=? ORDER BY id DESC LIMIT 2",
                         (video_id,))
        if len(rows) < 2:
            return None
        t1, t0 = (datetime.fromisoformat(r[0]) for r in rows)
        return {"views_delta": rows[0][1] - rows[1][1], "hours": round((t1 - t0).total_seconds() / 3600, 1)}

    def _card(self, r) -> dict:
        drafts = self._all("SELECT id,text,status,final_text FROM drafts WHERE video_id=? ORDER BY id",
                           (r["video_id"],))
        return {"video": json.loads(r["payload_json"]),
                "analysis": json.loads(r["analysis_json"]) if r["analysis_json"] else {},
                "drafts": [dict(d) for d in drafts], "growth": self.growth(r["video_id"]),
                "reported": r["reported_at"] is not None}

    def list_cards(self, limit: int = 20) -> list[dict]:
        rows = self._all("SELECT * FROM videos WHERE analysis_json IS NOT NULL "
                         "ORDER BY last_seen_at DESC, ratio DESC LIMIT ?", (limit,))
        return [self._card(r) for r in rows]

    def pending_delivery(self, limit: int) -> list[dict]:
        """Разобранные, но ещё не отправленные в Telegram. Лишние остаются на завтра."""
        rows = self._all("SELECT * FROM videos WHERE analysis_json IS NOT NULL AND reported_at IS NULL "
                         "ORDER BY ratio DESC, views DESC LIMIT ?", (limit,))
        return [self._card(r) for r in rows]

    def mark_reported(self, video_id: str) -> None:
        self._run("UPDATE videos SET reported_at=? WHERE video_id=?", (self.now(), video_id))

    def snapshot_count(self, video_id: str) -> int:
        return self._all("SELECT COUNT(*) FROM snapshots WHERE video_id=?", (video_id,))[0][0]

    # ---- черновики комментариев и обучение --------------------------------
    def add_draft(self, video_id: str, text: str) -> int:
        with self.lock:
            row = self.conn.execute("SELECT id FROM drafts WHERE video_id=? AND text=?", (video_id, text)).fetchone()
            if row:
                return int(row[0])
            cur = self.conn.execute("INSERT INTO drafts(video_id,text,status,created_at) VALUES(?,?,?,?)",
                                    (video_id, text, "proposed", self.now()))
            self.conn.commit()
            return int(cur.lastrowid)

    def set_feedback(self, draft_id: int, status: str, final_text: str | None = None) -> bool:
        if status not in ("accepted", "rejected", "edited"):
            raise ValueError("status: accepted | rejected | edited")
        if status == "edited" and not (final_text or "").strip():
            raise ValueError("для edited нужен итоговый текст")
        cur = self._run("UPDATE drafts SET status=?, final_text=? WHERE id=?",
                        (status, (final_text or "").strip() or None, draft_id))
        return cur.rowcount == 1

    def learned_style(self, limit: int = 20) -> list[str]:
        rows = self._all("SELECT COALESCE(final_text,text) FROM drafts WHERE status IN ('accepted','edited') "
                         "ORDER BY id DESC LIMIT ?", (limit,))
        return [r[0] for r in rows]

    # ---- мои ролики --------------------------------------------------------
    def upsert_own(self, url, platform, published_at, views, avg_view_pct, likes, comments, saves) -> None:
        self._run(
            """INSERT INTO own_videos(url,platform,published_at,views,avg_view_pct,likes,comments,saves,imported_at)
               VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET platform=excluded.platform,
               published_at=excluded.published_at, views=excluded.views, avg_view_pct=excluded.avg_view_pct,
               likes=excluded.likes, comments=excluded.comments, saves=excluded.saves,
               imported_at=excluded.imported_at""",
            (url, platform, published_at, views, avg_view_pct, likes, comments, saves, self.now()))

    def own_rows(self) -> list[dict]:
        return [dict(r) for r in self._all("SELECT * FROM own_videos")]

    # ---- разборы моих видеофайлов -----------------------------------------
    def save_video_audit(self, filename: str, hook_score: float, report: dict) -> int:
        return int(self._run("INSERT INTO video_audits(filename,hook_score,report_json,created_at) VALUES(?,?,?,?)",
                             (filename, hook_score, json.dumps(report, ensure_ascii=False), self.now())).lastrowid)

    def list_audits(self, limit: int = 20) -> list[dict]:
        return [{"id": r["id"], "filename": r["filename"], "hook_score": r["hook_score"],
                 "created_at": r["created_at"], "report": json.loads(r["report_json"])}
                for r in self._all("SELECT * FROM video_audits ORDER BY id DESC LIMIT ?", (limit,))]

    # ---- очередь публикаций СОБСТВЕННЫХ материалов (только с подтверждением) ----
    def queue_add(self, title, description, hashtags, platform, media_url=None) -> int:
        return int(self._run("INSERT INTO content_queue(title,description,hashtags,media_url,platform,status,created_at) "
                             "VALUES(?,?,?,?,?,'draft',?)",
                             (title, description, hashtags, media_url, platform, self.now())).lastrowid)

    def queue_get(self, item_id: int) -> dict | None:
        rows = self._all("SELECT * FROM content_queue WHERE id=?", (item_id,))
        return dict(rows[0]) if rows else None

    def queue_set(self, item_id: int, status: str, external_url: str | None = None, error: str | None = None) -> None:
        self._run("UPDATE content_queue SET status=?, external_url=COALESCE(?,external_url), error=? WHERE id=?",
                  (status, external_url, error, item_id))

    # ---- журнал запусков ----------------------------------------------------
    def start_run(self) -> int:
        return int(self._run("INSERT INTO runs(started_at,status) VALUES(?,?)", (self.now(), "running")).lastrowid)

    def finish_run(self, run_id: int, status: str, count: int = 0, error: str | None = None) -> None:
        self._run("UPDATE runs SET finished_at=?,status=?,reported_count=?,error=? WHERE id=?",
                  (self.now(), status, count, error, run_id))

    def close(self) -> None:
        with self.lock:
            self.conn.close()
