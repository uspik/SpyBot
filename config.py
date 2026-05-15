import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/bot.db"))
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "data/media"))
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "5"))
CLEANUP_INTERVAL_SEC = int(os.getenv("CLEANUP_INTERVAL_SEC", "3600"))

if not BOT_TOKEN:
    raise RuntimeError("Укажите BOT_TOKEN в .env или переменных окружения")
