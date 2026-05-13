
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BusinessConnection
import asyncio
import sqlite3
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)

bot = Bot(token="BOT_TOKEN")
dp = Dispatcher()

OWNER_ID: int | None = None

# ====================== База данных ======================
conn = sqlite3.connect('business_messages.db', check_same_thread=False)
cur = conn.cursor()
cur.execute('''
CREATE TABLE IF NOT EXISTS messages (
    chat_id INTEGER,
    message_id INTEGER,
    user_id INTEGER,
    user_name TEXT,
    text TEXT,
    date INTEGER,
    PRIMARY KEY (chat_id, message_id)
)
''')
conn.commit()


def save_message(message: types.Message):
    text = message.text or message.caption or "[Медиа без текста]"
    cur.execute('''
        INSERT OR REPLACE INTO messages 
        (chat_id, message_id, user_id, user_name, text, date)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (message.chat.id, message.message_id,
          message.from_user.id if message.from_user else None,
          message.from_user.full_name if message.from_user else None,
          text, int(message.date.timestamp())))
    conn.commit()


def get_message(chat_id: int, message_id: int):
    cur.execute("SELECT text, user_name FROM messages WHERE chat_id=? AND message_id=?",
                (chat_id, message_id))
    return cur.fetchone()


def update_message(chat_id: int, message_id: int, new_text: str):
    cur.execute('UPDATE messages SET text = ? WHERE chat_id = ? AND message_id = ?',
                (new_text, chat_id, message_id))
    conn.commit()


def delete_message_from_db(chat_id: int, message_id: int):
    cur.execute("DELETE FROM messages WHERE chat_id=? AND message_id=?",
                (chat_id, message_id))
    conn.commit()


def clean_old_messages():
    threshold = int((datetime.now() - timedelta(minutes=1)).timestamp())
    cur.execute("DELETE FROM messages WHERE date < ?", (threshold,))
    if cur.rowcount > 0:
        conn.commit()


# ====================== Обработчики ======================

@dp.business_connection()
async def on_business_connection(bc: BusinessConnection):
    global OWNER_ID
    OWNER_ID = bc.user.id
    logging.info(f"✅ Подключён к пользователю {OWNER_ID} ({bc.user.full_name})")

    try:
        await bot.send_message(
            bc.user_chat_id,
            "✅ <b>Мониторинг активирован!</b>\nЯ буду присылать уведомления об изменениях сюда.",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Ошибка приветствия: {e}")


@dp.business_message()
async def new_business_message(message: types.Message):
    save_message(message)
    clean_old_messages()


@dp.edited_business_message()
async def edited_handler(message: types.Message):
    global OWNER_ID
    if OWNER_ID is None:
        logging.warning("OWNER_ID is None")
        return

    try:
        old = get_message(message.chat.id, message.message_id)
        old_text = old[0] if old else "Не найдено в БД"
        new_text = message.text or message.caption or "[Медиа]"

        update_message(message.chat.id, message.message_id, new_text)

        link = get_chat_link(message.chat, message.message_id)

        text = (f"✏️ <b>Сообщение отредактировано</b>\n\n"
                f"👤 {message.from_user.full_name}\n"
                f"💬 <a href='{link}'>{message.chat.full_name or message.chat.title or 'ЛС'}</a>\n\n"
                f"<b>Было:</b>\n{old_text}\n\n"
                f"<b>Стало:</b>\n{new_text}")

        await bot.send_message(OWNER_ID, text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"Ошибка в edited_handler: {e}")


@dp.deleted_business_messages()
async def deleted_handler(event: types.BusinessMessagesDeleted):
    global OWNER_ID
    if OWNER_ID is None:
        return

    for msg_id in event.message_ids:
        try:
            old = get_message(event.chat.id, msg_id)
            old_text = old[0] if old else "Текст не сохранён"
            user_name = old[1] if old else "Неизвестно"

            link = get_chat_link(event.chat, msg_id)

            text = (f"🗑 <b>Сообщение удалено</b>\n\n"
                    f"👤 {user_name}\n"
                    f"💬 <a href='{link}'>{event.chat.full_name or event.chat.title or 'ЛС'}</a>\n\n"
                    f"<b>Текст:</b>\n{old_text}")

            await bot.send_message(OWNER_ID, text, parse_mode="HTML", disable_web_page_preview=True)
            delete_message_from_db(event.chat.id, msg_id)
        except Exception as e:
            logging.error(f"Ошибка удаления {msg_id}: {e}")


# ====================== Вспомогательные ======================

def get_chat_link(chat: types.Chat, message_id: int = None) -> str:
    if chat.type == "private":
        return f"tg://user?id={chat.id}"
    chat_id_str = str(chat.id).replace("-100", "")
    return f"https://t.me/c/{chat_id_str}/{message_id}" if message_id else f"https://t.me/c/{chat_id_str}"


@dp.message(Command("status"))
async def status(message: types.Message):
    await message.answer(
        f"✅ OWNER_ID: {OWNER_ID}\nБот работает"
        if OWNER_ID else "⏳ OWNER_ID ещё не получен.\n\nНапиши /connect"
    )


@dp.message(Command("connect"))
async def manual_connect(message: types.Message):
    """Ручная активация OWNER_ID"""
    global OWNER_ID
    OWNER_ID = message.from_user.id
    logging.info(f"🔧 Ручное подключение OWNER_ID = {OWNER_ID}")
    await message.answer("✅ OWNER_ID успешно установлен вручную!\nТеперь уведомления должны работать.")


async def main():
    print("🤖 Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())