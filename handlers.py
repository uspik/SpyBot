import logging

from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import db
import media_cache
from formatting import chat_label, escape, message_content, user_label

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Бот отслеживает <b>редактирование</b> и <b>удаление</b> чужих сообщений "
        "в ваших чатах через «Автоматизацию чатов».\n\n"
        "<b>Как подключить</b>\n"
        "1. Telegram → Настройки → Telegram для бизнеса → Чат-боты\n"
        "2. Добавьте этого бота\n\n"
        "Уведомления приходят сюда, в личный чат с ботом.\n"
        "Кэш сообщений хранится <b>5 дней</b>.\n"
        "Команда /status — проверить подключение."
    )
    if update.effective_message:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat:
        return
    rows = db.get_connection_by_owner(update.effective_chat.id)
    if not rows:
        await update.effective_message.reply_text(
            "Активных подключений нет. Подключите бота в настройках бизнес-аккаунта."
        )
        return

    lines = ["<b>Активные подключения</b>"]
    for row in rows:
        name = row["first_name"] or row["username"] or row["user_id"]
        lines.append(
            f"• {escape(str(name))} — id: <code>{escape(row['business_connection_id'])}</code>"
        )
    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML
    )


async def on_business_connection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    connection = update.business_connection
    if not connection:
        return

    user = connection.user
    db.upsert_connection(
        business_connection_id=connection.id,
        user_chat_id=connection.user_chat_id,
        user_id=user.id if user else None,
        username=user.username if user else None,
        first_name=user.first_name if user else None,
        is_enabled=connection.is_enabled,
        connected_at=connection.date,
    )

    if not connection.is_enabled:
        await context.bot.send_message(
            chat_id=connection.user_chat_id,
            text="Подключение к боту отключено. Уведомления больше не приходят.",
        )
        return

    await context.bot.send_message(
        chat_id=connection.user_chat_id,
        text=(
            "Бот подключён.\n"
            "Уведомления о редактировании и удалении <b>чужих</b> сообщений "
            "буду присылать сюда."
        ),
        parse_mode=ParseMode.HTML,
    )


async def on_business_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.business_message
    if not message or not message.business_connection_id:
        return
    await _store_message(context, message)


async def on_edited_business_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.edited_business_message
    if not message or not message.business_connection_id:
        return

    connection_id = message.business_connection_id
    owner_chat_id = db.get_owner_chat_id(connection_id)
    from_user_id = message.from_user.id if message.from_user else None
    is_foreign = db.is_foreign_message(connection_id, from_user_id)

    old_row = db.get_message(connection_id, message.chat_id, message.message_id)
    old_text = old_row["content"] if old_row else "(сообщение не было в кэше бота)"

    if is_foreign and owner_chat_id is not None:
        new_text = message_content(message)
        editor = user_label(message.from_user)
        chat_name = chat_label(message.chat)

        text = (
            f"✏️ <b>Сообщение отредактировано</b>\n"
            f"Чат: {chat_name}\n"
            f"Автор: {editor}\n\n"
            f"<b>Было:</b>\n{escape(old_text)}\n\n"
            f"<b>Стало:</b>\n{escape(new_text)}"
        )
        await context.bot.send_message(
            chat_id=owner_chat_id, text=text, parse_mode=ParseMode.HTML
        )
        if media_cache.message_has_file_media(message):
            await media_cache.send_edited_media(
                context,
                message,
                owner_chat_id,
                fallback_path=old_row["media_path"] if old_row else None,
            )

    await _store_message(context, message)


async def on_deleted_business_messages(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    payload = update.deleted_business_messages
    if not payload:
        return

    connection_id = payload.business_connection_id
    owner_chat_id = db.get_owner_chat_id(connection_id)
    chat = payload.chat
    rows = db.get_messages(connection_id, chat.id, list(payload.message_ids))

    foreign_rows = [
        row
        for row in rows
        if db.is_foreign_message(connection_id, row["from_user_id"])
    ]
    known_foreign_ids = {row["message_id"] for row in foreign_rows}

    if owner_chat_id is not None and foreign_rows:
        chat_name = chat_label(chat)
        blocks: list[str] = []
        for row in foreign_rows:
            author = row["from_username"]
            if author:
                author_label = f"@{escape(author)}"
            else:
                author_label = escape(row["from_first_name"] or "неизвестно")
            blocks.append(
                f"• id {row['message_id']} — {author_label}\n"
                f"{escape(row['content'])}"
            )

        for message_id in payload.message_ids:
            if message_id not in known_foreign_ids:
                row = next((r for r in rows if r["message_id"] == message_id), None)
                if row and not db.is_foreign_message(connection_id, row["from_user_id"]):
                    continue
                blocks.append(
                    f"• id {message_id} — текст не сохранён (бот не видел сообщение)"
                )

        text = (
            f"🗑 <b>Сообщения удалены</b>\n"
            f"Чат: {chat_name}\n"
            + "\n\n".join(blocks)
        )
        await context.bot.send_message(
            chat_id=owner_chat_id, text=text, parse_mode=ParseMode.HTML
        )

        for row in foreign_rows:
            if row["media_path"]:
                await media_cache.send_cached_file(
                    context,
                    owner_chat_id,
                    row["media_path"],
                    caption="Удалённое вложение",
                )

    media_paths = db.delete_messages(
        connection_id, chat.id, list(payload.message_ids)
    )
    for path in media_paths:
        media_cache.remove_media_file(path)


def perform_retention_cleanup() -> int:
    paths = db.purge_old_messages()
    for path in paths:
        media_cache.remove_media_file(path)
    if paths:
        logger.info("Очистка кэша: удалено записей с файлами: %s", len(paths))
    return len(paths)


async def _store_message(context: ContextTypes.DEFAULT_TYPE, message: Message) -> None:
    if not message.business_connection_id:
        return

    user = message.from_user
    from_user_id = user.id if user else None
    is_foreign = db.is_foreign_message(message.business_connection_id, from_user_id)

    media_path: str | None = None
    if is_foreign:
        if media_cache.message_has_file_media(message):
            downloaded = await media_cache.download_message_media(context, message)
            if downloaded:
                media_path = str(downloaded)
        elif message.edit_date:
            old = db.get_message(
                message.business_connection_id, message.chat.id, message.message_id
            )
            if old and old["media_path"]:
                media_path = old["media_path"]

    replaced = db.save_message(
        business_connection_id=message.business_connection_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
        from_user_id=from_user_id,
        from_username=user.username if user else None,
        from_first_name=user.first_name if user else None,
        chat_title=message.chat.title,
        chat_type=message.chat.type,
        content=message_content(message),
        message_date=message.date,
        media_path=media_path,
        keep_media_path=not is_foreign,
    )
    if replaced:
        media_cache.remove_media_file(replaced)
