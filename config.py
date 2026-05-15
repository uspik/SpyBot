from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return float(raw)


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/bot.db"))
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "data/media"))
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "5"))
CLEANUP_INTERVAL_SEC = int(os.getenv("CLEANUP_INTERVAL_SEC", "3600"))

# Таймауты для медленного VPS / нестабильной сети (секунды)
TELEGRAM_CONNECT_TIMEOUT = _float_env("TELEGRAM_CONNECT_TIMEOUT", 30.0)
TELEGRAM_READ_TIMEOUT = _float_env("TELEGRAM_READ_TIMEOUT", 30.0)
TELEGRAM_WRITE_TIMEOUT = _float_env("TELEGRAM_WRITE_TIMEOUT", 120.0)
TELEGRAM_POOL_TIMEOUT = _float_env("TELEGRAM_POOL_TIMEOUT", 30.0)
TELEGRAM_GET_UPDATES_READ_TIMEOUT = _float_env(
    "TELEGRAM_GET_UPDATES_READ_TIMEOUT", 60.0
)

# Если Telegram заблокирован: socks5://127.0.0.1:1080 или http://...
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "").strip() or None

if not BOT_TOKEN:
    raise RuntimeError("Укажите BOT_TOKEN в .env или переменных окружения")
