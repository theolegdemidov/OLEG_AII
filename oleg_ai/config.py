from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KEYWORDS = ["нейрохаризма", "харизма", "уверенность в себе", "самоконтроль"]


def load_dotenv(path: Path | None = None) -> None:
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _num(name: str, default, cast):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return cast(raw)
    except ValueError as exc:
        raise ValueError(f"{name} имеет неверное значение: {raw!r}") from exc


@dataclass(frozen=True)
class Config:
    youtube_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    llm_provider: str
    anthropic_api_key: str
    anthropic_model: str
    gemini_api_key: str
    gemini_model: str
    days_back: int
    min_views: int
    min_ratio: float
    subs_floor: int
    max_search_results: int
    top_n: int
    language: str
    api_token: str
    max_upload_mb: int
    pinterest_access_token: str
    pinterest_board_id: str
    channel_url: str


def get_config() -> Config:
    load_dotenv()
    g = lambda k, d="": os.getenv(k, d).strip()
    return Config(
        youtube_api_key=g("YOUTUBE_API_KEY"),
        telegram_bot_token=g("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=g("TELEGRAM_CHAT_ID"),
        llm_provider=g("LLM_PROVIDER", "anthropic").lower(),
        anthropic_api_key=g("ANTHROPIC_API_KEY"),
        anthropic_model=g("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        gemini_api_key=g("GEMINI_API_KEY"),
        gemini_model=g("GEMINI_MODEL", "gemini-2.5-flash"),
        days_back=_num("DAYS_BACK", 7, int),
        min_views=_num("MIN_VIEWS", 10_000, int),
        min_ratio=_num("MIN_RATIO", 3.0, float),
        subs_floor=_num("SUBSCRIBERS_FLOOR", 1000, int),
        max_search_results=_num("MAX_SEARCH_RESULTS_PER_KEYWORD", 15, int),
        top_n=_num("REPORT_TOP_N", 5, int),
        language=g("LANGUAGE", "ru") or "ru",
        api_token=g("API_TOKEN"),
        max_upload_mb=_num("MAX_UPLOAD_MB", 200, int),
        pinterest_access_token=g("PINTEREST_ACCESS_TOKEN"),
        pinterest_board_id=g("PINTEREST_BOARD_ID"),
        channel_url=g("TELEGRAM_CHANNEL_URL"),
    )


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [x.strip() for x in path.read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.lstrip().startswith("#")]


def load_keywords() -> list[str]:
    return read_lines(ROOT / "keywords.txt") or DEFAULT_KEYWORDS
