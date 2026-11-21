"""Статистика СОБСТВЕННЫХ роликов из CSV (экспорт YouTube Studio / ручная таблица).

Колонки: url, platform, published_at, views, avg_view_pct, likes, comments, saves.
Обязательны url и views. Остальное по желанию. Ничего не выдумываем: нет колонки, нет вывода.
"""
from __future__ import annotations

import csv
import re
import statistics
from datetime import datetime
from pathlib import Path

MIN_GROUP = 3  # меньше трёх роликов в группе: это шум, а не закономерность
DAYPARTS = [(5, 11, "утро 05-11"), (11, 17, "день 11-17"), (17, 23, "вечер 17-23")]


def _int(v):
    try:
        return int(float(str(v).replace(" ", "").replace(",", ".")))
    except (ValueError, TypeError):
        return None


def _float(v):
    try:
        return float(str(v).replace("%", "").replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


ALIASES = {
    "url": ["url", "link", "ссылка", "video url"],
    "video_id": ["video id", "video", "content", "контент", "id видео"],
    "platform": ["platform", "платформа"],
    "published_at": ["published_at", "video publish time", "время публикации видео", "дата публикации", "дата"],
    "views": ["views", "просмотры"],
    "avg_view_pct": ["avg_view_pct", "average percentage viewed (%)", "average percentage viewed",
                     "средний процент просмотра (%)", "средний процент просмотра"],
    "likes": ["likes", "лайки"],
    "comments": ["comments", "комментарии", "comments added"],
    "saves": ["saves", "сохранения"],
}
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _pick(row: dict, key: str) -> str:
    for name in ALIASES[key]:
        if row.get(name):
            return row[name]
    return ""


def import_csv(store, path: Path | str) -> int:
    """Понимает наш формат и (по возможности) экспорт YouTube Studio; заголовки Studio могут отличаться
    по языку и версии, поэтому нераспознанные строки пропускаются, а не угадываются."""
    n = 0
    with open(path, encoding="utf-8-sig", newline="") as f:
        head = f.readline()
        f.seek(0)
        delim = ";" if head.count(";") > head.count(",") else ","
        for row in csv.DictReader(f, delimiter=delim):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            views, url = _int(_pick(row, "views")), _pick(row, "url")
            if not url:
                vid = _pick(row, "video_id")
                url = f"https://www.youtube.com/watch?v={vid}" if _VIDEO_ID.match(vid) else ""
            if not url or views is None:
                continue
            store.upsert_own(url, _pick(row, "platform") or "unknown", _pick(row, "published_at") or None, views,
                             _float(_pick(row, "avg_view_pct")), _int(_pick(row, "likes")),
                             _int(_pick(row, "comments")), _int(_pick(row, "saves")))
            n += 1
    return n


_DATE_FORMATS = ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%b %d, %Y", "%Y-%m-%d")


def _parse_dt(value):
    """(datetime, есть_ли_время). Дата без времени не должна выглядеть как «ночь»."""
    v = (value or "").strip().replace("Z", "+00:00")
    if not v:
        return None, False
    try:
        t = datetime.fromisoformat(v)
        return t, len(v) > 10 and (t.hour or t.minute) != 0
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            t = datetime.strptime(v, fmt)
            return t, "%H" in fmt
        except ValueError:
            continue
    return None, False


WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def _daypart(hour: int) -> str | None:
    for a, b, name in DAYPARTS:
        if a <= hour < b:
            return name
    return "ночь 23-05"


def build_report(store) -> str:
    rows = store.own_rows()
    if not rows:
        return "Нет данных о твоих роликах. Импортируй CSV: python -m oleg_ai.main import-stats файл.csv"
    out = [f"МОИ РОЛИКИ: {len(rows)} шт. (по данным CSV)"]
    by_views = sorted(rows, key=lambda r: r["views"], reverse=True)
    med = statistics.median(r["views"] for r in rows)
    out.append(f"Медиана просмотров: {med:.0f}")
    out.append("Лучшие: " + "; ".join(f"{r['views']} - {r['url']}" for r in by_views[:3]))
    if len(rows) > 3:
        out.append("Слабые: " + "; ".join(f"{r['views']} - {r['url']}" for r in by_views[-3:]))
    ret = [r for r in rows if r["avg_view_pct"] is not None]
    if len(ret) >= MIN_GROUP:
        low = sorted(ret, key=lambda r: r["avg_view_pct"])[:3]
        out.append(f"Удержание: медиана {statistics.median(r['avg_view_pct'] for r in ret):.0f}%. "
                   "Хуже всего держат: " + "; ".join(f"{r['avg_view_pct']:.0f}% - {r['url']}" for r in low)
                   + ". Если удержание проседает в начале, переделывай хук.")
    else:
        out.append("Удержание: мало данных (нужна колонка avg_view_pct минимум у 3 роликов).")
    parsed = [(_parse_dt(r["published_at"]), r["views"]) for r in rows]
    parsed = [(t, has, v) for ((t, has), v) in parsed if t is not None]
    if parsed:
        with_time = all(has for _, has, _ in parsed)
        groups: dict[str, list[int]] = {}
        for t, _, v in parsed:
            groups.setdefault(_daypart(t.hour) if with_time else WEEKDAYS[t.weekday()], []).append(v)
        out.append("Время публикации (медиана просмотров):" if with_time
                   else "День недели публикации (в данных только даты, время суток недоступно; медиана просмотров):")
        for name in sorted(groups, key=lambda k: (WEEKDAYS.index(k) if k in WEEKDAYS else 0, k)):
            vals = groups[name]
            tag = f"{statistics.median(vals):.0f}" if len(vals) >= MIN_GROUP else "мало данных"
            out.append(f"  {name}: {tag} (роликов: {len(vals)})")
        out.append("Вывод о лучшем времени можно делать только когда в группе 3+ ролика. Это корреляция, не гарантия.")
    return "\n".join(out)
