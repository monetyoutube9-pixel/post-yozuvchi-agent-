"""Application settings loaded from .env (local) or os.environ (Railway)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Tuple

from dotenv import load_dotenv

DEFAULT_CHANNEL = "@aicreator_n1"
DEFAULT_SCHEDULE_TIME = "19:45"
DEFAULT_TIMEZONE = "Asia/Tashkent"
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"


class ConfigError(RuntimeError):
    """Raised when a required setting is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    gemini_api_key: str
    owner_id: int
    channel_username: str = DEFAULT_CHANNEL
    post_schedule_time: str = DEFAULT_SCHEDULE_TIME
    timezone: str = DEFAULT_TIMEZONE
    gemini_model: str = DEFAULT_GEMINI_MODEL

    @property
    def schedule_hour_minute(self) -> Tuple[int, int]:
        return parse_schedule_time(self.post_schedule_time)


def parse_schedule_time(value: str) -> Tuple[int, int]:
    """Parse an 'HH:MM' string into (hour, minute)."""
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value or "")
    if not match:
        raise ConfigError(f"POST_SCHEDULE_TIME must look like HH:MM, got {value!r}")
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ConfigError(f"POST_SCHEDULE_TIME out of range: {value!r}")
    return hour, minute


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> Settings:
    """Load settings from .env when present, falling back to real environment variables."""
    load_dotenv()  # does not override variables already set (e.g. on Railway)

    owner_raw = _require("OWNER_ID")
    try:
        owner_id = int(owner_raw)
    except ValueError as exc:
        raise ConfigError("OWNER_ID must be an integer Telegram user ID") from exc

    channel = os.environ.get("CHANNEL_USERNAME", DEFAULT_CHANNEL).strip() or DEFAULT_CHANNEL
    if not channel.startswith("@") and not channel.lstrip("-").isdigit():
        channel = "@" + channel

    schedule_time = os.environ.get("POST_SCHEDULE_TIME", DEFAULT_SCHEDULE_TIME).strip()
    parse_schedule_time(schedule_time)  # validate early

    return Settings(
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        gemini_api_key=_require("GEMINI_API_KEY"),
        owner_id=owner_id,
        channel_username=channel,
        post_schedule_time=schedule_time,
        timezone=os.environ.get("TIMEZONE", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE,
        gemini_model=os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
        or DEFAULT_GEMINI_MODEL,
    )
