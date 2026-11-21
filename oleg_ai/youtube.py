from __future__ import annotations

import datetime as dt
import re
import time

import requests

API = "https://www.googleapis.com/youtube/v3"
_DUR = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


class YouTubeError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, reason: str | None = None):
        super().__init__(message)
        self.status = status
        self.reason = reason


def duration_seconds(value: str | None) -> int | None:
    """ISO-8601 -> секунды. Пустое или нераспознанное значение даёт None, а не 0."""
    if not value:
        return None
    m = _DUR.match(value)
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


class YouTubeClient:
    def __init__(self, api_key: str, language: str = "ru", timeout: int = 25, retries: int = 3):
        if not api_key:
            raise YouTubeError("Не задан YOUTUBE_API_KEY")
        self.api_key, self.language, self.timeout, self.retries = api_key, language, timeout, retries
        self.session = requests.Session()

    def request(self, endpoint: str, **params) -> dict:
        params["key"] = self.api_key
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                r = self.session.get(f"{API}/{endpoint}", params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last = YouTubeError(f"Сетевая ошибка YouTube API: {exc}")
            else:
                if r.status_code < 400:
                    return r.json()
                reason, msg = None, r.text[:300]
                try:
                    err = r.json().get("error", {})
                    msg = err.get("message", msg)
                    reason = (err.get("errors") or [{}])[0].get("reason")
                except ValueError:
                    pass
                last = YouTubeError(f"YouTube API {r.status_code}: {msg}", r.status_code, reason)
                if r.status_code < 500 and r.status_code != 429:
                    raise last  # квота/ключ/запрос: повтор не поможет
            time.sleep(2 ** attempt)
        raise last  # type: ignore[misc]

    def search_ids(self, query: str, published_after: str, limit: int) -> list[str]:
        data = self.request("search", part="snippet", type="video", videoDuration="short",
                            order="viewCount", publishedAfter=published_after, q=query,
                            relevanceLanguage=self.language, maxResults=min(limit, 50))
        return [x["id"]["videoId"] for x in data.get("items", []) if "videoId" in x.get("id", {})]

    def videos(self, ids: list[str]) -> list[dict]:
        out: list[dict] = []
        for i in range(0, len(ids), 50):
            out += self.request("videos", part="snippet,statistics,contentDetails",
                                id=",".join(ids[i:i + 50])).get("items", [])
        return out

    def channels(self, ids: list[str]) -> dict[str, int | None]:
        out: dict[str, int | None] = {}
        uniq = list(dict.fromkeys(ids))
        for i in range(0, len(uniq), 50):
            for c in self.request("channels", part="statistics",
                                  id=",".join(uniq[i:i + 50])).get("items", []):
                st = c.get("statistics", {})
                out[c["id"]] = None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0))
        return out

    def comments(self, video_id: str, limit: int = 8) -> tuple[list[str], str | None]:
        try:
            data = self.request("commentThreads", part="snippet", videoId=video_id,
                                order="relevance", maxResults=min(limit, 100), textFormat="plainText")
        except YouTubeError as exc:
            if exc.reason == "commentsDisabled":
                return [], "Комментарии отключены автором"
            return [], f"Ошибка получения комментариев: {exc}"
        return [i["snippet"]["topLevelComment"]["snippet"].get("textDisplay", "")[:500]
                for i in data.get("items", [])], None


def _age_days(published: str, now: dt.datetime) -> float:
    try:
        t = dt.datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return 7.0
    return max((now - t).total_seconds() / 86400, 0.5)


def discover(client, keywords, days_back, limit, min_views, min_ratio, subs_floor=1000, now=None) -> list[dict]:
    now = now or dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    kw_by_id: dict[str, str] = {}
    for kw in keywords:
        for vid in client.search_ids(kw, since, limit):
            kw_by_id.setdefault(vid, kw)
    if not kw_by_id:
        return []
    raw = client.videos(list(kw_by_id))
    subs = client.channels([v["snippet"]["channelId"] for v in raw])
    out = []
    for v in raw:
        sn, st = v.get("snippet", {}), v.get("statistics", {})
        views = int(st.get("viewCount", 0))
        s = subs.get(sn.get("channelId", ""))
        if s is None or views < min_views:
            continue
        ratio = views / max(s, subs_floor)  # пол защищает от x1000 на каналах с 0 подписчиков
        if ratio < min_ratio:
            continue
        sec = duration_seconds(v.get("contentDetails", {}).get("duration"))
        out.append({
            "id": v["id"], "title": sn.get("title", "(без названия)"),
            "channel": sn.get("channelTitle", ""), "channel_id": sn.get("channelId", ""),
            "description": sn.get("description", "")[:1200],
            "views": views, "subs": s, "ratio": round(ratio, 2),
            "views_per_day": round(views / _age_days(sn.get("publishedAt", ""), now)),
            "published": sn.get("publishedAt", ""), "keyword": kw_by_id[v["id"]],
            "duration_seconds": sec,
            "format_hint": "short_form_candidate" if sec is not None and sec <= 180 else "short_video_or_unknown",
            "url": f"https://www.youtube.com/watch?v={v['id']}",
            "shorts_url": f"https://www.youtube.com/shorts/{v['id']}",
        })
    out.sort(key=lambda x: (x["ratio"], x["views"]), reverse=True)
    return out
