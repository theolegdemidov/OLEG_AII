from __future__ import annotations

from .analyzer import analyze, normalize
from .youtube import discover


def run_research(cfg, yt, store, *, keywords, style, analyze_fn=analyze) -> dict:
    """Поиск -> снимки статистики -> разбор ТОЛЬКО ещё не разобранных роликов.

    Повторный запуск не тратит квоту LLM на уже разобранное и не плодит дубли черновиков.
    Если LLM упал, ролик остаётся неразобранным и будет повторён в следующий раз.
    """
    items = discover(yt, keywords, cfg.days_back, cfg.max_search_results, cfg.min_views,
                     cfg.min_ratio, cfg.subs_floor)
    for it in items:
        store.record(it)
    full_style = store.learned_style() + style  # сначала то, что ты уже одобрил/исправил
    analyzed = failed = 0
    last_error = None
    for item in store.unanalyzed(cfg.top_n):
        comments, _ = yt.comments(item["id"])
        res = analyze_fn(item, comments, full_style, cfg)
        if not res["ok"]:
            failed += 1
            last_error = res["raw"][:300]
            continue
        data = normalize(res["data"])
        store.save_analysis(item["id"], data)
        for text in data["comments"]:
            store.add_draft(item["id"], text)
        analyzed += 1
    return {"found": len(items), "analyzed": analyzed, "failed": failed, "error": last_error}
