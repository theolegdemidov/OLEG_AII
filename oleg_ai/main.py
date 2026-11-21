from __future__ import annotations

import argparse
import json
import sys

from .analyzer import analyze
from .config import ROOT, get_config, load_keywords, read_lines
from .own_stats import build_report, import_csv
from .research import run_research
from .storage import Store
from .telegram import send_report
from .youtube import YouTubeClient

LIMIT = 3800


def format_card(card: dict) -> str:
    v, a = card["video"], card["analysis"]
    sec = v.get("duration_seconds")
    head = [v["title"],
            f"{v['channel']} | {v['views']:,} просм. / {v['subs']:,} подп. (x{v['ratio']}), ~{v.get('views_per_day', '?')}/день",
            f"Дата: {v['published'][:10]} | {f'{sec} сек.' if sec is not None else 'длительность неизвестна'} | {v['format_hint']}",
            v["shorts_url"]]
    g = card.get("growth")
    if g:
        head.append(f"Рост с прошлого замера: +{g['views_delta']:,} за {g['hours']} ч.")
    body = []
    if a.get("facts"):
        body.append("ФАКТЫ:\n" + "\n".join(f"- {x}" for x in a["facts"]))
    if a.get("hypotheses"):
        body.append("ГИПОТЕЗЫ (не доказано):\n" + "\n".join(f"- {x}" for x in a["hypotheses"]))
    if a.get("ab_hooks"):
        body.append("A/B-ХУКИ:\n" + "\n".join(f"- {x}" for x in a["ab_hooks"]))
    if a.get("ideas"):
        body.append("ИДЕИ АНИМАЦИЙ:\n" + "\n".join(
            f"{n}. Хук: {i['hook']}\n   Суть: {i['thesis']}\n   Визуал: {i['visual']}\n   CTA: {i['cta']}"
            for n, i in enumerate(a["ideas"], 1)))
    if card["drafts"]:
        body.append("ЧЕРНОВИКИ КОММЕНТАРИЕВ (публикуешь сам; оценка: feedback <№> accepted|rejected|edited):\n"
                    + "\n".join(f"#{d['id']} {d['text']}" for d in card["drafts"]))
    if a.get("missing_data"):
        body.append("НЕ ХВАТАЕТ ДАННЫХ: " + "; ".join(a["missing_data"]))
    return ("\n".join(head) + "\n\n" + "\n\n".join(body))[:LIMIT]


def deliver(store, send_fn, limit: int, dry_run: bool = False) -> list[str]:
    """Один ролик = одно сообщение. Помечаем отправленным только после успешной доставки именно его."""
    texts = []
    for card in store.pending_delivery(limit):
        text = format_card(card)
        if not dry_run:
            send_fn(text)
            store.mark_reported(card["video"]["id"])
        texts.append(text)
    return texts


def _open() -> Store:
    return Store(ROOT / "oleg_ai.db")


def cmd_research(args) -> int:
    cfg = get_config()
    if not cfg.youtube_api_key:
        sys.exit("Заполни YOUTUBE_API_KEY в .env")
    store = _open()
    run_id = store.start_run()
    try:
        yt = YouTubeClient(cfg.youtube_api_key, language=cfg.language)
        res = run_research(cfg, yt, store, keywords=load_keywords(),
                           style=read_lines(ROOT / "style_examples.txt"), analyze_fn=analyze)
        print(f"Найдено: {res['found']}, разобрано: {res['analyzed']}, ошибок LLM: {res['failed']}")
        if res["error"]:
            print("Последняя ошибка LLM:", res["error"])
        store.finish_run(run_id, "success", res["analyzed"])
        return 0
    except Exception as exc:
        store.finish_run(run_id, "failed", 0, str(exc))
        raise
    finally:
        store.close()


def cmd_deliver(args) -> int:
    cfg = get_config()
    store = _open()
    try:
        texts = deliver(store, lambda t: send_report(cfg.telegram_bot_token, cfg.telegram_chat_id, t),
                        cfg.top_n, args.dry_run)
        if args.dry_run:
            print(("\n\n" + "-" * 35 + "\n\n").join(texts) or "Нечего отправлять.")
            print("\n[DRY RUN] Telegram не вызывался, ничего не помечено отправленным.")
        else:
            print(f"Отправлено сообщений: {len(texts)}")
        if args.json:
            (ROOT / "findings.json").write_text(json.dumps(store.list_cards(100), ensure_ascii=False, indent=2),
                                                encoding="utf-8")
        return 0
    finally:
        store.close()


def cmd_run(args) -> int:
    cmd_research(args)
    return cmd_deliver(args)


def cmd_feedback(args) -> int:
    store = _open()
    try:
        ok = store.set_feedback(args.draft_id, args.status, args.text)
    finally:
        store.close()
    print("Принято. Это попадёт в профиль твоего стиля." if ok else "Черновик не найден.")
    return 0 if ok else 1


def cmd_import(args) -> int:
    store = _open()
    try:
        print(f"Импортировано роликов: {import_csv(store, args.path)}")
    finally:
        store.close()
    return 0


def cmd_own_report(args) -> int:
    store = _open()
    try:
        text = build_report(store)
    finally:
        store.close()
    print(text)
    if args.send:
        cfg = get_config()
        send_report(cfg.telegram_bot_token, cfg.telegram_chat_id, text)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="oleg_ai", description="OLEG AI")
    p.add_argument("--dry-run", action="store_true", help="не отправлять в Telegram и ничего не помечать")
    p.add_argument("--json", action="store_true", help="сохранить карточки в findings.json")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("research", help="только поиск и разбор")
    sub.add_parser("deliver", help="только отправка разобранного в Telegram")
    f = sub.add_parser("feedback", help="оценить черновик комментария")
    f.add_argument("draft_id", type=int)
    f.add_argument("status", choices=["accepted", "rejected", "edited"])
    f.add_argument("text", nargs="?", help="итоговый текст (для edited)")
    i = sub.add_parser("import-stats", help="импорт CSV со статистикой своих роликов")
    i.add_argument("path")
    o = sub.add_parser("own-report", help="разбор своих роликов")
    o.add_argument("--send", action="store_true")
    args = p.parse_args(argv)
    return {"research": cmd_research, "deliver": cmd_deliver, "feedback": cmd_feedback,
            "import-stats": cmd_import, "own-report": cmd_own_report}.get(args.command, cmd_run)(args)


if __name__ == "__main__":
    sys.exit(main())
