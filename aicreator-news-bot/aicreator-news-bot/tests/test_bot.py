"""Offline unit tests: no network, no real Telegram or Gemini calls."""
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest

from news_bot import scheduler as sched
from news_bot.config import ConfigError, Settings, load_settings, parse_schedule_time
from news_bot.gemini_service import NewsPost, parse_response, to_telegram_html
from news_bot.media_service import clean_text_for_speech, generate_3d_image_url


def make_settings(**overrides):
    base = dict(
        telegram_bot_token="123:test",
        gemini_api_key="test-key",
        owner_id=7380564381,
    )
    base.update(overrides)
    return Settings(**base)


# ---- config ----------------------------------------------------------------

def test_parse_schedule_time_valid():
    assert parse_schedule_time("19:45") == (19, 45)
    assert parse_schedule_time("7:05") == (7, 5)


@pytest.mark.parametrize("bad", ["", "25:00", "19-45", "19:60"])
def test_parse_schedule_time_invalid(bad):
    with pytest.raises(ConfigError):
        parse_schedule_time(bad)


def test_load_settings_defaults(monkeypatch):
    monkeypatch.setattr("news_bot.config.load_dotenv", lambda: None)
    for name in ("CHANNEL_USERNAME", "POST_SCHEDULE_TIME", "TIMEZONE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("OWNER_ID", "7380564381")
    s = load_settings()
    assert s.channel_username == "@aicreator_n1"
    assert s.post_schedule_time == "19:45"
    assert s.timezone == "Asia/Tashkent"
    assert s.owner_id == 7380564381


def test_load_settings_missing_required(monkeypatch):
    monkeypatch.setattr("news_bot.config.load_dotenv", lambda: None)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("OWNER_ID", "1")
    with pytest.raises(ConfigError):
        load_settings()


# ---- gemini_service --------------------------------------------------------

def test_to_telegram_html_bold_and_escape():
    assert to_telegram_html("**Sarlavha** a < b & c") == "<b>Sarlavha</b> a &lt; b &amp; c"


def test_parse_response_json_and_fence():
    raw = '```json\n{"post": "**Salom**", "image_prompt": "a robot"}\n```'
    post = parse_response(raw)
    assert post.text == "**Salom**"
    assert post.image_prompt == "a robot"


def test_parse_response_plain_text_fallback():
    post = parse_response("Oddiy matn")
    assert post.text == "Oddiy matn"
    assert post.image_prompt


def test_parse_response_empty_raises():
    with pytest.raises(ValueError):
        parse_response('{"post": "", "image_prompt": "x"}')


# ---- media_service ---------------------------------------------------------

def test_image_url_contains_style():
    url = generate_3d_image_url("a friendly robot")
    assert url.startswith("https://image.pollinations.ai/prompt/")
    assert "Pixar" in url and "octane" in url and "8k" in url


def test_clean_text_for_speech():
    cleaned = clean_text_for_speech("**Salom** _dunyo_ # test\n#yangiliklar #tech")
    assert "*" not in cleaned and "#" not in cleaned and "_" not in cleaned
    assert "yangiliklar" not in cleaned
    assert "Salom" in cleaned


# ---- scheduler -------------------------------------------------------------

def test_keyboard_layout():
    kb = sched.build_keyboard()
    first, second = kb.inline_keyboard
    assert [b.text for b in first] == ["👍 Zo'r", "🔥 Muhim"]
    assert second[0].url == "https://t.me/aicreator_n1"


def test_setup_scheduler_registers_job():
    s = sched.setup_scheduler(MagicMock(), make_settings())
    job = s.get_job(sched.JOB_ID)
    assert job is not None
    assert "19" in str(job.trigger) and "45" in str(job.trigger)


async def test_publish_news_sends_photo_and_voice(monkeypatch):
    monkeypatch.setattr(
        sched, "generate_news_post",
        AsyncMock(return_value=NewsPost(text="**Yangilik** matni #tech", image_prompt="robot")),
    )
    monkeypatch.setattr(sched, "download_image", AsyncMock(return_value=b"jpegbytes"))
    voice = BytesIO(b"oggbytes")
    voice.name = "voice.ogg"
    monkeypatch.setattr(sched, "generate_voice_message", lambda text: voice)

    bot = MagicMock()
    bot.send_photo = AsyncMock()
    bot.send_voice = AsyncMock()
    bot.send_message = AsyncMock()

    await sched.publish_news(bot, make_settings(), "@aicreator_n1")

    bot.send_photo.assert_awaited_once()
    assert "<b>Yangilik</b>" in bot.send_photo.await_args.kwargs["caption"]
    bot.send_voice.assert_awaited_once()
    bot.send_message.assert_not_awaited()


async def test_publish_news_text_only_when_image_fails(monkeypatch):
    monkeypatch.setattr(
        sched, "generate_news_post",
        AsyncMock(return_value=NewsPost(text="**A**", image_prompt="x")),
    )
    monkeypatch.setattr(sched, "download_image", AsyncMock(return_value=None))
    monkeypatch.setattr(sched, "generate_voice_message", lambda text: None)

    bot = MagicMock()
    bot.send_photo = AsyncMock()
    bot.send_message = AsyncMock()

    await sched.publish_news(bot, make_settings(), 1)

    bot.send_photo.assert_not_awaited()
    bot.send_message.assert_awaited_once()
