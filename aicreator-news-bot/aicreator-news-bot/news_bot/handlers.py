"""Telegram command and callback handlers."""
from __future__ import annotations

import logging
from typing import Dict, Set, Tuple

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import Settings
from .scheduler import build_keyboard, next_run_text, publish_news

logger = logging.getLogger(__name__)
router = Router()

# In-memory reaction counters (reset on restart/redeploy).
_counts: Dict[Tuple[int, int], Dict[str, int]] = {}
_voters: Dict[Tuple[int, int], Set[Tuple[int, str]]] = {}


@router.message(Command("start"))
async def cmd_start(message: Message, settings: Settings, scheduler: AsyncIOScheduler) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if user_id == settings.owner_id:
        await message.answer(
            "👋 Salom, egasi!\n\n"
            f"✅ Bot ishlayapti.\n"
            f"📢 Kanal: {settings.channel_username}\n"
            f"🕖 Kunlik e'lon vaqti: {settings.post_schedule_time} ({settings.timezone})\n"
            f"⏭ Keyingi e'lon: {next_run_text(scheduler)}\n"
            f"🆔 Sizning ID: <code>{user_id}</code>\n\n"
            "Buyruqlar:\n"
            "/test — darhol test postini (rasm + matn + ovozli xabar) shu yerga yuboradi\n"
            "/start — bot holatini ko'rsatadi"
        )
    else:
        await message.answer(
            f"Assalomu alaykum! Men {settings.channel_username} kanalining yordamchi botiman. "
            "Har kuni dunyo va texnologiya yangiliklarini o'qish uchun kanalimizga obuna bo'ling: "
            "https://t.me/aicreator_n1"
        )


@router.message(Command("test"))
async def cmd_test(message: Message, settings: Settings) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if user_id != settings.owner_id:
        await message.answer("⛔ Bu buyruq faqat bot egasi uchun.")
        return
    await message.answer("⏳ Test posti tayyorlanmoqda, bir oz kuting...")
    try:
        await publish_news(message.bot, settings, message.chat.id)
    except Exception as exc:
        logger.exception("/test failed")
        await message.answer(
            f"❌ Xatolik: {type(exc).__name__}: {exc}", parse_mode=None
        )


@router.callback_query(F.data.startswith("react:"))
async def on_reaction(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    kind = callback.data.split(":", 1)[1]
    key = (callback.message.chat.id, callback.message.message_id)
    voter = (callback.from_user.id, kind)

    voters = _voters.setdefault(key, set())
    if voter in voters:
        await callback.answer("Siz allaqachon bosgansiz 🙂")
        return
    voters.add(voter)
    counts = _counts.setdefault(key, {"good": 0, "hot": 0})
    counts[kind] = counts.get(kind, 0) + 1

    try:
        await callback.message.edit_reply_markup(
            reply_markup=build_keyboard(counts["good"], counts["hot"])
        )
    except Exception:
        logger.debug("Could not update reaction buttons", exc_info=True)
    await callback.answer("Rahmat! 🙌")
