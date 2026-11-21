from __future__ import annotations

import requests


def split_message(text: str, limit: int = 3800) -> list[str]:
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        while len(para) > limit:  # одна очень длинная часть
            if cur:
                chunks.append(cur); cur = ""
            chunks.append(para[:limit]); para = para[limit:]
        if len(cur) + len(para) + 2 > limit and cur:
            chunks.append(cur); cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        chunks.append(cur)
    return chunks or ["Пустой отчёт"]


def send_report(token: str, chat_id: str, text: str) -> None:
    if not token or not chat_id:
        raise RuntimeError("Не заданы TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID")
    for chunk in split_message(text):
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
                          timeout=25)
        if r.status_code >= 400:
            raise RuntimeError(f"Telegram API {r.status_code}: {r.text[:300]}")
