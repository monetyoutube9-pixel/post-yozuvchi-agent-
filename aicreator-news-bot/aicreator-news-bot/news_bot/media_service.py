"""Media helpers: 3D-style illustration URL (Pollinations) and voice message (gTTS)."""
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import subprocess
from io import BytesIO
from typing import Optional, Tuple
from urllib.parse import quote

import requests
from gtts import gTTS

logger = logging.getLogger(__name__)

STYLE_SUFFIX = "Pixar style 3D render, highly detailed, octane render, 8k resolution"
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"
VOICE_LANG = "uz"
VOICE_FALLBACK_LANG = "tr"  # used only if the installed gTTS does not support Uzbek
DEFAULT_NEURONAI_VOICE = "kamron"


def generate_3d_image_url(prompt_text: str) -> str:
    """Build a Pollinations image URL for a detailed 3D-render illustration."""
    subject = re.sub(r"[*#_`]+", "", prompt_text or "").strip()
    subject = re.sub(r"\s+", " ", subject)[:300] or "technology news"
    full_prompt = f"{subject}, {STYLE_SUFFIX}"
    seed = random.randint(1, 10_000_000)
    return (
        POLLINATIONS_URL.format(prompt=quote(full_prompt))
        + f"?width=1280&height=720&nologo=true&seed={seed}"
    )


def _fetch_image(url: str, timeout: int = 120) -> Optional[bytes]:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    if not response.headers.get("content-type", "").startswith("image/"):
        raise ValueError("Pollinations did not return an image")
    return response.content


async def download_image(url: str, attempts: int = 3) -> Optional[bytes]:
    """Download the generated image so Telegram does not have to wait for rendering."""
    for attempt in range(1, attempts + 1):
        try:
            return await asyncio.to_thread(_fetch_image, url)
        except Exception as exc:
            logger.warning("Image download attempt %d/%d failed: %s", attempt, attempts, exc)
            await asyncio.sleep(2 * attempt)
    return None


def clean_text_for_speech(text: str) -> str:
    """Remove markdown markers and hashtags so they are not read aloud."""
    cleaned = re.sub(r"#\w+", "", text)  # hashtags
    cleaned = re.sub(r"[*#_`]+", "", cleaned)  # markdown characters
    return re.sub(r"\s+", " ", cleaned).strip()


def _mp3_to_ogg_opus(mp3_bytes: bytes) -> Optional[bytes]:
    """Convert mp3 to OGG/Opus (Telegram voice format) with ffmpeg; None if unavailable."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", "pipe:0",
             "-c:a", "libopus", "-b:a", "48k", "-f", "ogg", "pipe:1"],
            input=mp3_bytes,
            capture_output=True,
            timeout=60,
            check=True,
        )
        return result.stdout or None
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        logger.warning("ffmpeg conversion failed: %s", exc)
        return None


def _synthesize_neuronai(text: str) -> Tuple[bytes, str]:
    """Uzbek speech from NeuronAI (default voice: 'kamron'). Returns (WAV bytes, 'wav')."""
    from naiuz import NeuronAI  # imported lazily so the bot still starts without the package

    voice_id = os.environ.get("NEURONAI_VOICE_ID", "").strip() or DEFAULT_NEURONAI_VOICE
    client = NeuronAI()  # reads NEURONAI_API_KEY from the environment
    speech = client.tts.synthesize(text=text, voice_id=voice_id, language="uz")
    return speech.audio, "wav"


def _synthesize_gtts(text: str) -> Tuple[bytes, str]:
    buffer = BytesIO()
    try:
        gTTS(text=text, lang=VOICE_LANG).write_to_fp(buffer)
    except (ValueError, AssertionError):
        logger.warning("gTTS lacks '%s'; falling back to '%s'", VOICE_LANG, VOICE_FALLBACK_LANG)
        buffer = BytesIO()
        gTTS(text=text, lang=VOICE_FALLBACK_LANG).write_to_fp(buffer)
    return buffer.getvalue(), "mp3"


def _synthesize(text: str) -> Tuple[bytes, str]:
    """Prefer NeuronAI when NEURONAI_API_KEY is set; otherwise (or on failure) use gTTS."""
    if os.environ.get("NEURONAI_API_KEY", "").strip():
        try:
            return _synthesize_neuronai(text)
        except Exception as exc:
            logger.warning("NeuronAI synthesis failed (%s); falling back to gTTS", exc)
    return _synthesize_gtts(text)


def generate_voice_message(text: str) -> Optional[BytesIO]:
    """Turn post text into a voice message stream.

    Returns a BytesIO named 'voice.ogg' (OGG/Opus) when ffmpeg is available,
    otherwise 'voice.wav' / 'voice.mp3'. Returns None if speech synthesis fails.
    """
    speech_text = clean_text_for_speech(text)
    if not speech_text:
        return None
    try:
        audio_bytes, extension = _synthesize(speech_text)
    except Exception as exc:
        logger.error("Voice synthesis failed: %s", exc)
        return None

    ogg_bytes = _mp3_to_ogg_opus(audio_bytes)  # ffmpeg detects wav/mp3 input automatically
    stream = BytesIO(ogg_bytes or audio_bytes)
    stream.name = "voice.ogg" if ogg_bytes else f"voice.{extension}"
    return stream
