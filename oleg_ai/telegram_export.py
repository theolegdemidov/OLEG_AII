"""Анализ ЭКСПОРТА СВОЕГО Telegram-канала (Telegram Desktop -> Экспорт истории чата -> JSON).

Своя реализация на стандартной библиотеке. Идеи (время активности, частоты слов) общие, код не заимствован.
Работает только с текстом и числами ваших же постов: ничего не скачивает из сети, не извлекает
телефоны, e-mail и данные других людей.

Запуск: python -m oleg_ai.telegram_export result.json
Формат экспорта я не мог проверить на живом файле, поэтому разбор терпимый: нет поля, нет вывода.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

MIN_GROUP = 3
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
DAYPARTS = [(5, 11, "утро 05-11"), (11, 17, "день 11-17"), (17, 23, "вечер 17-23")]
LENGTHS = [(0, 200, "короткие до 200 символов"), (200, 600, "средние 200-600"), (600, 10**9, "длинные от 600")]
STOP = set("""это как что для при или так его все она они были быть есть уже ещё еще только если когда
который которые которая этот эта эти того тому чтобы потому именно очень можно нужно надо будет тебя тебе мне
меня тоже даже более менее после перед между через себя свой свои""".split())


def _text(raw) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return "".join(p if isinstance(p, str) else str(p.get("text", "")) for p in raw if isinstance(p, (str, dict)))
    return ""


def _reactions(msg: dict) -> int:
    total = 0
    for r in msg.get("reactions") or []:
        if isinstance(r, dict):
            try:
                total += int(r.get("count", 0))
            except (TypeError, ValueError):
                pass
    return total


def load_posts(path: Path | str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    msgs = data.get("messages") if isinstance(data, dict) else None
    if msgs is None and isinstance(data, dict):  # полный экспорт аккаунта: берём первый чат с сообщениями
        for chat in (data.get("chats") or {}).get("list", []):
            if chat.get("messages"):
                msgs = chat["messages"]
                break
    posts = []
    for m in msgs or []:
        if not isinstance(m, dict) or m.get("type", "message") != "message":
            continue
        try:
            when = datetime.fromisoformat(str(m.get("date", "")))
        except ValueError:
            continue
        views = m.get("views")
        posts.append({"id": m.get("id"), "when": when, "text": _text(m.get("text")),
                      "reactions": _reactions(m), "views": views if isinstance(views, int) else None})
    return posts


def choose_metric(posts: list[dict]) -> str:
    with_views = sum(1 for p in posts if p["views"] is not None)
    return "views" if posts and with_views * 2 >= len(posts) else "reactions"


def _daypart(h: int) -> str:
    return next((n for a, b, n in DAYPARTS if a <= h < b), "ночь 23-05")


def _group(posts, metric, key):
    g: dict[str, list[int]] = defaultdict(list)
    for p in posts:
        g[key(p)].append(p[metric] or 0)
    return g


def _fmt_group(title: str, g: dict[str, list[int]], order=None) -> list[str]:
    out = [title]
    for k in sorted(g, key=order or (lambda x: x)):
        v = g[k]
        val = f"{statistics.median(v):.0f}" if len(v) >= MIN_GROUP else "мало данных"
        out.append(f"  {k}: {val} (постов: {len(v)})")
    return out


def words_in_top(posts, metric) -> list[tuple[str, int]]:
    ranked = sorted(posts, key=lambda p: p[metric] or 0, reverse=True)
    top = ranked[: max(MIN_GROUP, len(ranked) // 4)]
    cnt: Counter = Counter()
    for p in top:
        cnt.update({w for w in re.findall(r"[а-яёa-z]{4,}", p["text"].lower()) if w not in STOP})
    return [(w, c) for w, c in cnt.most_common(40) if c >= MIN_GROUP][:12]


def build_report(posts: list[dict]) -> str:
    if len(posts) < 5:
        return "Слишком мало постов для выводов (нужно хотя бы 5). Проверь, что экспортирован нужный канал в формате JSON."
    metric = choose_metric(posts)
    label = "просмотры" if metric == "views" else "реакции (просмотров в экспорте нет)"
    vals = [p[metric] or 0 for p in posts]
    out = [f"КАНАЛ: {len(posts)} постов, {posts[0]['when']:%d.%m.%Y}-{posts[-1]['when']:%d.%m.%Y}",
           f"Метрика: {label}. Медиана: {statistics.median(vals):.0f}"]
    out += _fmt_group("По дням недели (медиана):", _group(posts, metric, lambda p: WEEKDAYS[p["when"].weekday()]),
                      lambda k: WEEKDAYS.index(k))
    out += _fmt_group("По времени суток (время как в экспорте, обычно местное):",
                      _group(posts, metric, lambda p: _daypart(p["when"].hour)))
    out += _fmt_group("По длине поста:", _group(posts, metric, lambda p: next(n for a, b, n in LENGTHS if a <= len(p["text"]) < b)))
    tags: dict[str, list[int]] = defaultdict(list)
    for p in posts:
        for t in set(re.findall(r"#\w+", p["text"].lower())):
            tags[t].append(p[metric] or 0)
    good = {t: v for t, v in tags.items() if len(v) >= MIN_GROUP}
    if good:
        out.append("Хэштеги (3+ постов, медиана):")
        out += [f"  {t}: {statistics.median(v):.0f} (постов: {len(v)})"
                for t, v in sorted(good.items(), key=lambda kv: -statistics.median(kv[1]))[:8]]
    ranked = sorted(posts, key=lambda p: p[metric] or 0, reverse=True)
    snip = lambda p: f"{p[metric] or 0} - {p['text'][:70].strip().replace(chr(10), ' ')}"
    out += ["Лучшие посты:"] + [f"  {snip(p)}" for p in ranked[:5]]
    out += ["Слабые посты:"] + [f"  {snip(p)}" for p in ranked[-5:]]
    words = words_in_top(posts, metric)
    if words:
        out.append("Слова, часто встречающиеся в лучших 25% постов (3+ раза): " + ", ".join(f"{w} ({c})" for w, c in words))
    out.append("Это корреляции по вашей истории, не причины и не гарантия. Группы меньше 3 постов помечены «мало данных».")
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Использование: python -m oleg_ai.telegram_export result.json")
    print(build_report(load_posts(sys.argv[1])))
