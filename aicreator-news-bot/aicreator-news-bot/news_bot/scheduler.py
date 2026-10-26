"""Daily publishing logic and APScheduler integration."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional, Union

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Settings
from .gemini_service import generate_news_post, to_telegram_html
from .media_service import download_image, generate_3d_image_url, generate_voice_message

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024
CHANNEL_URL = "https://t.me/aicreator_n1"
JOB_ID = "daily_news"


def build_keyboard(good: int = 0, hot: int = 0) -> InlineKeyboardMarkup:
    """Reaction buttons plus a subscribe link."""
    good_label = "👍 Zo'r" + (f" · {good}" if good else "")
    hot_label = "🔥 Muhim" + (f" · {hot}" if hot else "")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=good_label, callback_data="react:good"),
                InlineKeyboardButton(text=hot_label, callback_data="react:hot"),
            ],
            [InlineKeyboardButton(text="📢 Kanalimizga obuna bo'lish", url=CHANNEL_URL)],
        ]
    )


async def publish_news(bot: Bot, settings: Settings, chat_id: Union[int, str]) -> None:
    """Generate and send one post (3D image + bold text + buttons) followed by a voice message."""
    post = await generate_news_post(settings)
    caption = to_telegram_html(post.text)
    keyboard = build_keyboard()

    # Images are off by default (Pollinations now requires payment); set ENABLE_IMAGE=1 to turn them on.
    image = None
    if os.environ.get("ENABLE_IMAGE", "").strip().lower() in ("1", "true", "yes"):
        image = await download_image(generate_3d_image_url(post.image_prompt))

    if image and len(caption) <= CAPTION_LIMIT:
        await bot.send_photo(
            chat_id,
            BufferedInputFile(image, filename="news.jpg"),
            caption=caption,
            reply_markup=keyboard,
        )
    elif image:  # caption too long: image first, full text as a separate message
        await bot.send_photo(chat_id, BufferedInputFile(image, filename="news.jpg"))
        await bot.send_message(chat_id, caption, reply_markup=keyboard)
    else:
        logger.warning("Image unavailable, sending text-only post")
        await bot.send_message(chat_id, caption, reply_markup=keyboard)

    # Voice is off by default; set ENABLE_VOICE=1 to send a voice message after the post.
    if os.environ.get("ENABLE_VOICE", "").strip().lower() not in ("1", "true", "yes"):
        return
    voice = await asyncio.to_thread(generate_voice_message, post.text)
    if voice is None:
        logger.warning("Voice message skipped")
        return
    data = BufferedInputFile(voice.getvalue(), filename=voice.name)
    if voice.name.endswith(".ogg"):
        await bot.send_voice(chat_id, data)
    else:  # ffmpeg missing: mp3 cannot be a voice note, send as audio
        await bot.send_audio(chat_id, data)


async def publish_daily_news(bot: Bot, settings: Settings) -> None:
    """Scheduled job: publish to the channel and alert the owner on failure."""
    logger.info("Publishing daily news to %s", settings.channel_username)
    try:
        await publish_news(bot, settings, settings.channel_username)
        logger.info("Daily news published")
    except Exception as exc:
        logger.exception("Daily publish failed")
        try:
            await bot.send_message(
                settings.owner_id,
                f"⚠️ Kunlik yangilikni e'lon qilishda xatolik yuz berdi:\n{type(exc).__name__}: {exc}",
                parse_mode=None,
            )
        except Exception:
            logger.exception("Could not notify the owner")


def setup_scheduler(bot: Bot, settings: Settings) -> AsyncIOScheduler:
    """Create the scheduler with the daily cron job (not started yet)."""
    hour, minute = settings.schedule_hour_minute
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        publish_daily_news,
        CronTrigger(hour=hour, minute=minute, timezone=settings.timezone),
        args=[bot, settings],
        id=JOB_ID,
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    return scheduler


def next_run_text(scheduler: Optional[AsyncIOScheduler]) -> str:
    job = scheduler.get_job(JOB_ID) if scheduler else None
    nxt = getattr(job, "next_run_time", None)
    return nxt.strftime("%Y-%m-%d %H:%M %Z") if nxt else "noma'lum"
