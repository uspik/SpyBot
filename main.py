import asyncio
import logging

from telegram.ext import (
    Application,
    BusinessConnectionHandler,
    BusinessMessagesDeletedHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

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


async def _retention_loop() -> None:
    await asyncio.sleep(30)
    while True:
        try:
            perform_retention_cleanup()
        except Exception:
            logger.exception("Ошибка фоновой очистки кэша")
        await asyncio.sleep(config.CLEANUP_INTERVAL_SEC)


async def post_init(_application: Application) -> None:
    perform_retention_cleanup()
    asyncio.create_task(_retention_loop())


def main() -> None:
    db.init_db()

    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

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

    allowed = [
        "business_connection",
        "business_message",
        "edited_business_message",
        "deleted_business_messages",
        "message",
    ]

    logger.info("Бот запущен (хранение кэша: %s дн.)", config.RETENTION_DAYS)
    application.run_polling(allowed_updates=allowed)


if __name__ == "__main__":
    main()
