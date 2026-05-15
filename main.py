from __future__ import annotations

import asyncio
import logging

from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    Application,
    BusinessConnectionHandler,
    BusinessMessagesDeletedHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

import config
import db
from handlers import (
    cmd_start,
    cmd_status,
    on_business_connection,
    on_business_message,
    on_deleted_business_messages,
    on_edited_business_message,
    perform_retention_cleanup,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
_retention_task: asyncio.Task | None = None


def _build_application() -> Application:
    request = HTTPXRequest(
        connect_timeout=config.TELEGRAM_CONNECT_TIMEOUT,
        read_timeout=config.TELEGRAM_READ_TIMEOUT,
        write_timeout=config.TELEGRAM_WRITE_TIMEOUT,
        pool_timeout=config.TELEGRAM_POOL_TIMEOUT,
        proxy=config.TELEGRAM_PROXY_URL,
    )
    get_updates_request = HTTPXRequest(
        connect_timeout=config.TELEGRAM_CONNECT_TIMEOUT,
        read_timeout=config.TELEGRAM_GET_UPDATES_READ_TIMEOUT,
        write_timeout=config.TELEGRAM_WRITE_TIMEOUT,
        pool_timeout=config.TELEGRAM_POOL_TIMEOUT,
        proxy=config.TELEGRAM_PROXY_URL,
    )

    builder = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .request(request)
        .get_updates_request(get_updates_request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
    )
    if config.TELEGRAM_PROXY_URL:
        logger.info("Используется прокси для Telegram API")
    return builder.build()


async def _retention_loop() -> None:
    await asyncio.sleep(30)
    while True:
        try:
            perform_retention_cleanup()
        except Exception:
            logger.exception("Ошибка фоновой очистки кэша")
        await asyncio.sleep(config.CLEANUP_INTERVAL_SEC)


async def post_init(_application: Application) -> None:
    global _retention_task
    perform_retention_cleanup()
    _retention_task = asyncio.create_task(_retention_loop())


async def post_shutdown(_application: Application) -> None:
    global _retention_task
    if _retention_task and not _retention_task.done():
        _retention_task.cancel()
        try:
            await _retention_task
        except asyncio.CancelledError:
            pass
    _retention_task = None


async def on_error(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    error = context.error
    if isinstance(error, (TimedOut, NetworkError)):
        logger.warning("Таймаут/сеть Telegram (бот продолжает работу): %s", error)
        return
    logger.error("Ошибка обработки update: %s", error, exc_info=error)


def main() -> None:
    db.init_db()

    application = _build_application()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(BusinessConnectionHandler(on_business_connection))
    application.add_handler(
        MessageHandler(filters.UpdateType.BUSINESS_MESSAGE, on_business_message)
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.EDITED_BUSINESS_MESSAGE, on_edited_business_message
        )
    )
    application.add_handler(
        BusinessMessagesDeletedHandler(on_deleted_business_messages)
    )
    application.add_error_handler(on_error)

    allowed = [
        "business_connection",
        "business_message",
        "edited_business_message",
        "deleted_business_messages",
        "message",
    ]

    logger.info(
        "SpyBot запущен | python-telegram-bot | кэш %s дн.",
        config.RETENTION_DAYS,
    )
    application.run_polling(
        allowed_updates=allowed,
        drop_pending_updates=True,
        bootstrap_retries=-1,
        close_loop=False,
    )


if __name__ == "__main__":
    main()
