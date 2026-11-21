# Без `from __future__ import annotations`: FastAPI/pydantic разбирают аннотации во время выполнения.
import tempfile
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import own_stats
from .analyzer import analyze
from .config import ROOT, get_config, load_keywords, read_lines
from .publisher import publish_pinterest_pin
from .research import run_research
from .service import ResearchJob, UploadError, append_style, check_token, save_upload
from .storage import Store
from .video_lab import analyze_video_file
from .youtube import YouTubeClient


class FeedbackIn(BaseModel):
    draft_id: int
    status: Literal["accepted", "rejected", "edited"]
    final_text: Optional[str] = Field(default=None, max_length=500)


class StyleIn(BaseModel):
    phrase: str = Field(max_length=300)


class QueueIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=500)
    hashtags: str = Field(default="", max_length=200)
    platform: Literal["pinterest"] = "pinterest"
    image_url: str = Field(max_length=1000)


def create_app(cfg=None, store=None) -> FastAPI:
    cfg = cfg or get_config()
    if not cfg.api_token or len(cfg.api_token) < 16:
        raise RuntimeError("Задай API_TOKEN (минимум 16 символов) в .env. Без пароля сервер не запускается.")
    store = store or Store(ROOT / "oleg_ai.db")
    job = ResearchJob()
    app = FastAPI(title="OLEG AI Local Producer API", version="1.3.0")

    def auth(x_api_key: Optional[str] = Header(default=None)):
        if not check_token(x_api_key, cfg.api_token):
            raise HTTPException(status_code=401, detail="Неверный или отсутствующий X-API-Key")

    guard = [Depends(auth)]

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/cards", dependencies=guard)
    def cards(limit: int = 20):
        return {"items": store.list_cards(limit=max(1, min(limit, 100)))}

    def _research():
        if not cfg.youtube_api_key:
            raise RuntimeError("Не задан YOUTUBE_API_KEY")
        yt = YouTubeClient(cfg.youtube_api_key, language=cfg.language)
        return run_research(cfg, yt, store, keywords=load_keywords(),
                            style=read_lines(ROOT / "style_examples.txt"), analyze_fn=analyze)

    @app.post("/research/run", dependencies=guard)
    def research_run():
        started = job.start(_research)
        return {"started": started, "status": job.snapshot()}

    @app.get("/research/status", dependencies=guard)
    def research_status():
        return job.snapshot()

    @app.post("/feedback", dependencies=guard)
    def feedback(body: FeedbackIn):
        try:
            ok = store.set_feedback(body.draft_id, body.status, body.final_text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not ok:
            raise HTTPException(status_code=404, detail="Черновик не найден")
        return {"ok": True}

    @app.post("/style", dependencies=guard)
    def style(body: StyleIn):
        try:
            added = append_style(ROOT / "style_examples.txt", body.phrase)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True, "added": added}

    # обычный def: FastAPI выполнит в пуле потоков, долгий анализ не блокирует остальные запросы
    @app.post("/video/analyze", dependencies=guard)
    def video_analyze(file: UploadFile = File(...)):
        try:
            path = save_upload(file.file, Path(tempfile.gettempdir()) / "oleg_ai_uploads", file.filename,
                               cfg.max_upload_mb * (1 << 20))
        except UploadError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        try:
            report = analyze_video_file(path, cfg)
        finally:
            path.unlink(missing_ok=True)
        if report.get("ok"):
            store.save_video_audit(file.filename or "video", float(report["hook_score"]), report)
        return report

    @app.get("/video/audits", dependencies=guard)
    def audits(limit: int = 20):
        return {"items": store.list_audits(max(1, min(limit, 100)))}

    @app.post("/own/import", dependencies=guard)
    def own_import(file: UploadFile = File(...)):
        data = file.file.read(2 * (1 << 20) + 1)
        if len(data) > 2 * (1 << 20):
            raise HTTPException(status_code=400, detail="CSV больше 2 МБ")
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(data)
        try:
            n = own_stats.import_csv(store, tmp.name)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
        return {"ok": True, "imported": n}

    @app.get("/own/report", dependencies=guard)
    def own_report():
        return {"text": own_stats.build_report(store)}

    # Публикация своих материалов: создать -> явно одобрить -> опубликовать. Ничего автоматически.
    @app.post("/queue", dependencies=guard)
    def queue_add(body: QueueIn):
        return {"id": store.queue_add(body.title, body.description, body.hashtags, body.platform, body.image_url)}

    @app.post("/queue/{item_id}/approve", dependencies=guard)
    def queue_approve(item_id: int):
        item = store.queue_get(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Не найдено")
        if item["status"] != "draft":
            raise HTTPException(status_code=409, detail=f"Статус {item['status']}, одобрить нельзя")
        store.queue_set(item_id, "approved")
        return {"ok": True}

    @app.post("/queue/{item_id}/publish", dependencies=guard)
    def queue_publish(item_id: int):
        item = store.queue_get(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Не найдено")
        if item["status"] != "approved":
            raise HTTPException(status_code=409, detail="Сначала одобри публикацию")
        store.queue_set(item_id, "publishing")  # защита от двойного нажатия
        try:
            res = publish_pinterest_pin(cfg.pinterest_access_token, cfg.pinterest_board_id, item["title"],
                                        f"{item['description']} {item['hashtags']}".strip(),
                                        item["media_url"] or "", cfg.channel_url)
        except Exception as exc:  # noqa: BLE001
            store.queue_set(item_id, "approved", error=str(exc)[:300])
            raise HTTPException(status_code=502, detail=str(exc)[:300])
        store.queue_set(item_id, "published", external_url=str(res.get("id", "")))
        return {"ok": True, "pin": res.get("id")}

    return app
