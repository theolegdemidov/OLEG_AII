"""Простое меню для Windows: запускается двойным щелчком по START.bat.

Первый запуск сам спрашивает ключи и создаёт файл .env. Дальше меню из пяти пунктов, ничего вводить в терминале не нужно.
"""
from __future__ import annotations

import csv
import os
import re
import secrets
import shutil
import socket
import sys
from pathlib import Path

from .config import ROOT

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}


def clean_path(raw: str) -> Path:
    """Путь, перетащенный в окно консоли, приходит в кавычках."""
    return Path(raw.strip().strip('"').strip("'"))


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # пакет не отправляется, нужен только выбор сетевого интерфейса
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def set_env_values(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in values and "=" in line and not line.lstrip().startswith("#"):
            lines[i] = f"{key}={values[key]}"
            done.add(key)
    lines += [f"{k}={v}" for k, v in values.items() if k not in done]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_env(path: Path, example: Path, ask=input) -> bool:
    """Создаёт .env при первом запуске. Возвращает True, если файл был создан сейчас."""
    if path.exists():
        return False
    if example.exists():
        shutil.copyfile(example, path)
    print("Первый запуск: ответь на три вопроса. Любой можно пропустить клавишей Enter и заполнить позже.\n")
    values = {"API_TOKEN": secrets.token_urlsafe(32)}  # пароль для телефона создаётся сам
    print("1) Какой ИИ использовать для текстов?  1 = Claude (платный ключ), 2 = Gemini (есть бесплатный ключ, aistudio.google.com)")
    choice = ask("   Введи 1 или 2: ").strip()
    if choice == "2":
        key = ask("   Вставь ключ Gemini: ").strip()
        values["LLM_PROVIDER"] = "gemini"
        if key:
            values["GEMINI_API_KEY"] = key
    else:
        key = ask("   Вставь ключ Claude (или Enter): ").strip()
        values["LLM_PROVIDER"] = "anthropic"
        if key:
            values["ANTHROPIC_API_KEY"] = key
    yt = ask("2) Ключ YouTube API (нужен только для поиска трендов, можно пропустить): ").strip()
    if yt:
        values["YOUTUBE_API_KEY"] = yt
    link = ask("3) Ссылка на твой Telegram-канал для описаний (или Enter): ").strip()
    if link:
        values["TELEGRAM_CHANNEL_URL"] = link
    set_env_values(path, values)
    print("\nГотово, настройки сохранены в .env.\n")
    return True


def scan_folder(folder: Path, out_csv: Path) -> list[dict]:
    """Список видео из папки превращается в videos.csv: тема берётся из названия файла."""
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT)
    rows = [{"file": p.name, "topic": re.sub(r"[_\-]+", " ", p.stem).strip()} for p in files]
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "topic"])
        w.writeheader()
        w.writerows(rows)
    return rows


def _open(path: Path) -> None:
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]  # только Windows
    except (AttributeError, OSError):
        print("Открой файл вручную:", path)


def menu_pack(ask=input) -> None:
    from . import packs
    folder = clean_path(ask("Перетащи сюда папку с готовыми видео и нажми Enter: "))
    if not folder.is_dir():
        print("Папка не найдена.")
        return
    rows = scan_folder(folder, ROOT / "videos.csv")
    if not rows:
        print("В папке нет видео (mp4, mov, m4v, webm).")
        return
    print(f"Найдено роликов: {len(rows)}. Темы взяты из названий файлов (можно поправить в videos.csv).")
    start = ask("С какой даты публиковать (ГГГГ-ММ-ДД) или Enter, чтобы с завтрашнего дня: ").strip()
    args = [str(ROOT / "videos.csv")] + (["--start", start] if start else [])
    packs.main(args)
    _open(Path.cwd() / "pack.md")


def menu_trends() -> None:
    from . import main as app
    if not os.getenv("YOUTUBE_API_KEY"):
        print("Нужен ключ YouTube API. Впиши его в .env (инструкция в README) и запусти снова.")
        return
    app.main(["research"])
    app.main(["--dry-run", "deliver"])


def menu_channel(ask=input) -> None:
    from . import main as app
    csv_path = clean_path(ask("Перетащи сюда CSV из YouTube Studio и нажми Enter: "))
    if not csv_path.is_file():
        print("Файл не найден.")
        return
    app.main(["import-stats", str(csv_path)])
    app.main(["own-report"])


def menu_phone() -> None:
    from .config import get_config
    cfg = get_config()
    ip = local_ip()
    print("\nВ приложении на телефоне открой вкладку «Настройки» и впиши:")
    print(f"  Адрес:  http://{ip}:8000")
    print(f"  Пароль: {cfg.api_token}")
    print("\nТелефон и ноутбук должны быть в одной Wi-Fi сети. Если Windows спросит про доступ, нажми «Разрешить».")
    print("Пока это окно открыто, телефон работает. Чтобы остановить, закрой окно.\n")
    import uvicorn
    uvicorn.run("oleg_ai.server:create_app", factory=True, host="0.0.0.0", port=8000)


MENU = """
===== OLEG AI =====
 1. Подготовить публикации на неделю (названия, описания, расписание)
 2. Найти тренды в моей нише
 3. Разобрать мой канал (CSV из YouTube Studio)
 4. Связать с телефоном
 5. Выход
"""


def main(ask=input) -> int:
    from .config import load_dotenv
    ensure_env(ROOT / ".env", ROOT / ".env.example", ask)
    load_dotenv()
    actions = {"1": lambda: menu_pack(ask), "2": menu_trends, "3": lambda: menu_channel(ask), "4": menu_phone}
    while True:
        print(MENU)
        choice = ask("Выбери номер: ").strip()
        if choice == "5":
            return 0
        action = actions.get(choice)
        if not action:
            print("Нужна цифра от 1 до 5.")
            continue
        try:
            action()
        except KeyboardInterrupt:
            print("\nОстановлено.")
        except Exception as exc:  # noqa: BLE001 - меню не должно закрываться молча
            print(f"Ошибка: {exc}")
        ask("\nНажми Enter, чтобы вернуться в меню...")


if __name__ == "__main__":
    sys.exit(main())
