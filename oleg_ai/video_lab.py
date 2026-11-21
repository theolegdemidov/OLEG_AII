"""Разбор СВОЕГО видеофайла через Gemini (мультимодально: речь, текст на экране, темп, хук)."""
from __future__ import annotations

import time
from pathlib import Path

from .analyzer import extract_json

PROMPT = """Ты продюсер вертикальных видео (Shorts / Reels / TikTok) для мужского мотивационного бренда «Уверенность в действии».
Посмотри и послушай это видео целиком (русский язык). Оцени строго и конструктивно.
Не придумывай того, чего нет в видео. Верни ТОЛЬКО JSON без markdown:
{
  "hook_score": число от 0 до 10,
  "first_2_sec_verdict": "что происходит в первые 2 секунды и удержит ли это зрителя",
  "transcript_summary": "краткая суть озвучки и текста на экране",
  "weak_spots": ["конкретный момент (с таймкодом, если видно), где зритель может свайпнуть"],
  "improved_hooks": ["2 более сильных первых фразы для A/B-теста"],
  "best_title_and_tags": "заголовок и 5 хэштегов"
}"""


def _state(f) -> str:
    st = getattr(f, "state", None)
    return str(getattr(st, "name", st) or "").split(".")[-1].upper()


def _score(value) -> float:
    try:
        return max(0.0, min(10.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def analyze_video_file(path: Path, cfg, *, client=None, sleep=time.sleep, max_wait: float = 240) -> dict:
    if client is None:
        if not cfg.gemini_api_key:
            return {"ok": False, "hook_score": 0.0, "error": "Для анализа видеофайлов задай GEMINI_API_KEY в .env"}
        from google import genai  # ленивый импорт: сервер стартует и без этого пакета
        client = genai.Client(api_key=cfg.gemini_api_key)
    uploaded = None
    try:
        uploaded = client.files.upload(file=str(path))
        waited = 0.0
        while _state(uploaded) == "PROCESSING":  # видео обрабатывается асинхронно, без ожидания будет ошибка
            if waited >= max_wait:
                return {"ok": False, "hook_score": 0.0, "error": "Gemini слишком долго обрабатывает видео"}
            sleep(3)
            waited += 3
            uploaded = client.files.get(name=uploaded.name)
        if _state(uploaded) == "FAILED":
            return {"ok": False, "hook_score": 0.0, "error": "Gemini не смог обработать этот файл"}
        response = client.models.generate_content(model=cfg.gemini_model, contents=[uploaded, PROMPT])
        text = getattr(response, "text", "") or ""
        data = extract_json(text)
        if not data:
            return {"ok": False, "hook_score": 0.0, "error": "Ответ не в формате JSON", "raw": text[:500]}
        return {"ok": True, "hook_score": _score(data.get("hook_score")),
                "first_2_sec_verdict": str(data.get("first_2_sec_verdict", ""))[:600],
                "transcript_summary": str(data.get("transcript_summary", ""))[:800],
                "weak_spots": [str(x)[:300] for x in (data.get("weak_spots") or [])][:6],
                "improved_hooks": [str(x)[:200] for x in (data.get("improved_hooks") or [])][:3],
                "best_title_and_tags": str(data.get("best_title_and_tags", ""))[:300]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "hook_score": 0.0, "error": f"{type(exc).__name__}: {exc}"[:300]}
    finally:
        if uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:  # noqa: BLE001
                pass
