"""Публикация СВОИХ материалов через официальный Pinterest API v5. Только пины-картинки.

Пины-видео в API требуют отдельной загрузки медиа и не реализованы в этой версии.
Вызывается только из подтверждённого владельцем элемента очереди.
"""
from __future__ import annotations

import requests


def publish_pinterest_pin(access_token: str, board_id: str, title: str, description: str,
                          image_url: str, link: str = "") -> dict:
    if not access_token or not board_id:
        raise RuntimeError("Не заданы PINTEREST_ACCESS_TOKEN и PINTEREST_BOARD_ID")
    if not image_url.startswith("https://"):
        raise ValueError("image_url должен быть публичной https-ссылкой на картинку")
    body = {"board_id": board_id, "title": title[:100], "description": description[:500],
            "media_source": {"source_type": "image_url", "url": image_url}}
    if link:
        body["link"] = link
    r = requests.post("https://api.pinterest.com/v5/pins",
                      headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                      json=body, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Pinterest API {r.status_code}: {r.text[:300]}")
    return r.json()
