from __future__ import annotations

import logging
from pathlib import Path

from telegram import Message
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from config import MEDIA_DIR
from formatting import _media_type

logger = logging.getLogger(__name__)


def local_media_path(
    business_connection_id: str, chat_id: int, message_id: int
) -> Path:
    folder = MEDIA_DIR / business_connection_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{chat_id}_{message_id}"


def message_has_file_media(message: Message) -> bool:
    return bool(
        message.photo
        or message.video
        or message.voice
        or message.audio
        or message.document
        or message.animation
        or message.video_note
    )


async def download_message_media(
    context: ContextTypes.DEFAULT_TYPE, message: Message
) -> Path | None:
    if not message_has_file_media(message):
        return None

    tg_file = None
    ext = ".bin"

    if message.photo:
        tg_file = await message.photo[-1].get_file()
        ext = ".jpg"
    elif message.video:
        tg_file = await message.video.get_file()
        ext = Path(message.video.file_name or ".mp4").suffix or ".mp4"
    elif message.voice:
        tg_file = await message.voice.get_file()
        ext = ".ogg"
    elif message.audio:
        tg_file = await message.audio.get_file()
        ext = Path(message.audio.file_name or ".mp3").suffix or ".mp3"
    elif message.document:
        tg_file = await message.document.get_file()
        ext = Path(message.document.file_name or ".bin").suffix or ".bin"
    elif message.animation:
        tg_file = await message.animation.get_file()
        ext = ".mp4"
    elif message.video_note:
        tg_file = await message.video_note.get_file()
        ext = ".mp4"

    if tg_file is None:
        return None

    if not message.business_connection_id:
        return None

    path = local_media_path(
        message.business_connection_id, message.chat_id, message.message_id
    ).with_suffix(ext)

    try:
        await tg_file.download_to_drive(custom_path=str(path))
        return path
    except TelegramError as exc:
        logger.warning("Не удалось скачать медиа %s: %s", path, exc)
        return None


async def send_edited_media(
    context: ContextTypes.DEFAULT_TYPE,
    message: Message,
    owner_chat_id: int,
    fallback_path: str | None = None,
) -> bool:
    """PTB не передаёт business_connection_id в copy_message — шлём скачанный файл."""
    if not message_has_file_media(message):
        return False

    caption = media_caption_hint(message) or "Актуальная версия"
    downloaded = await download_message_media(context, message)
    if downloaded and await send_cached_file(
        context, owner_chat_id, str(downloaded), caption=caption
    ):
        return True

    if fallback_path:
        return await send_cached_file(
            context, owner_chat_id, fallback_path, caption="Версия из кэша"
        )
    return False


async def send_cached_file(
    context: ContextTypes.DEFAULT_TYPE,
    owner_chat_id: int,
    media_path: str,
    caption: str | None = None,
) -> bool:
    path = Path(media_path)
    if not path.is_file():
        return False

    suffix = path.suffix.lower()
    try:
        with path.open("rb") as handle:
            if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
                await context.bot.send_photo(
                    chat_id=owner_chat_id, photo=handle, caption=caption
                )
            elif suffix in {".mp4", ".mov"}:
                await context.bot.send_video(
                    chat_id=owner_chat_id, video=handle, caption=caption
                )
            elif suffix == ".ogg":
                await context.bot.send_voice(
                    chat_id=owner_chat_id, voice=handle, caption=caption
                )
            elif suffix in {".mp3", ".m4a", ".wav"}:
                await context.bot.send_audio(
                    chat_id=owner_chat_id, audio=handle, caption=caption
                )
            else:
                await context.bot.send_document(
                    chat_id=owner_chat_id, document=handle, caption=caption
                )
        return True
    except TelegramError as exc:
        logger.warning("Не удалось отправить файл %s: %s", path, exc)
        return False


def remove_media_file(media_path: str | None) -> None:
    if not media_path:
        return
    path = Path(media_path)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Не удалось удалить %s: %s", path, exc)


def media_caption_hint(message: Message) -> str | None:
    if not message_has_file_media(message):
        return None
    label = _media_type(message)
    return f"Копия: {label}"
