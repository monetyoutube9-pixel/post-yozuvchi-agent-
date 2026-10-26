# Gemini AI News Assistant Bot

A Telegram bot that publishes one Uzbek-language world & technology news post to the
channel **@aicreator_n1** every day at **19:45 (Asia/Tashkent)**.

Each post contains:

1. A 3D-render style illustration (Pollinations AI),
2. A journalistic Uzbek text written by Google Gemini, with bold headline and keywords and 3-4 hashtags,
3. Inline buttons: `👍 Zo'r`, `🔥 Muhim`, `📢 Kanalimizga obuna bo'lish`,
4. A follow-up voice message (gTTS) reading the post aloud.

## How it works

- `news_bot/gemini_service.py` fetches fresh headlines from public RSS feeds and asks Gemini Flash to pick
  the best story and write the post (plus an English image prompt) as JSON.
- `news_bot/media_service.py` builds the Pollinations 3D image URL, downloads the image, and converts the
  post text to speech (gTTS -> mp3 -> OGG/Opus through ffmpeg).
- `news_bot/scheduler.py` runs `publish_daily_news()` with APScheduler (`AsyncIOScheduler`, cron).
- `news_bot/handlers.py` implements `/start`, `/test` (owner only) and the reaction buttons.
- `bot.py` is the entry point with graceful SIGINT/SIGTERM shutdown.

## Configuration

| Variable | Rule |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Required. Token from @BotFather |
| `GEMINI_API_KEY` | Required. Google Gemini API key |
| `OWNER_ID` | Required. Owner's Telegram ID (`7380564381`) |
| `CHANNEL_USERNAME` | Default `@aicreator_n1` |
| `POST_SCHEDULE_TIME` | Default `19:45` |
| `TIMEZONE` | Default `Asia/Tashkent` |
| `GEMINI_MODEL` | Optional, default `gemini-flash-latest` |

Locally the values are read from `.env`; on Railway they come from the service Variables.
Never commit `.env` (it is in `.gitignore`).

## Step-by-step setup

### 1. Telegram

1. Create a bot with @BotFather and copy the token.
2. Add the bot to **@aicreator_n1** as an administrator with the "Post messages" permission.

### 2. Local test

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # then fill in TELEGRAM_BOT_TOKEN and GEMINI_API_KEY
python bot.py
```

Send `/start` and then `/test` to the bot from the owner account to receive a sample post.
For voice messages in the Telegram voice format, `ffmpeg` must be installed locally
(`brew install ffmpeg` / `apt install ffmpeg`). Without it the bot sends the audio as an mp3 file instead.

Run the tests:

```bash
pytest
```

### 3. Deploy to Railway

1. Create a **private** GitHub repository and push this project.
2. In Railway create a new project and connect the repository. `railway.json` selects the Dockerfile builder,
   and every push redeploys automatically.
3. In the service **Variables** add `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `OWNER_ID=7380564381`
   and `CHANNEL_USERNAME=@aicreator_n1`.

## Notes

- Reaction counters on the buttons are kept in memory and reset when the bot restarts.
- gTTS may not support Uzbek in every version; the bot then falls back to a Turkish voice
  (Latin script, similar pronunciation) and logs a warning.
- If image generation fails, the post is sent as text only; if the owner-visible job fails, the owner gets a Telegram alert.
