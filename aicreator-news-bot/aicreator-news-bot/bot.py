"""Entry point: wires up Bot, Dispatcher and the daily scheduler."""
from __future__ import annotations

import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from news_bot.config import load_settings
from news_bot.handlers import router
from news_bot.scheduler import setup_scheduler

logger = logging.getLogger("bot")


async def main() -> None:
    settings = load_settings()

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    scheduler = setup_scheduler(bot, settings)
    # Injected into handlers by parameter name.
    dp["settings"] = settings
    dp["scheduler"] = scheduler

    # Graceful shutdown on SIGINT / SIGTERM (Railway sends SIGTERM on redeploy).
    loop = asyncio.get_running_loop()

    def _request_stop() -> None:
        logger.info("Shutdown signal received, stopping polling...")
        asyncio.ensure_future(dp.stop_polling())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:  # e.g. Windows
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(_request_stop))

    scheduler.start()
    logger.info(
        "Scheduler started: daily post at %s (%s) -> %s",
        settings.post_schedule_time, settings.timezone, settings.channel_username,
    )

    try:
        await dp.start_polling(bot, handle_signals=False)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Bot stopped cleanly")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
