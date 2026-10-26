"""Gemini integration: collects headlines and writes the Uzbek news post."""
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List

import google.generativeai as genai
import requests

from .config import Settings

logger = logging.getLogger(__name__)

# Public RSS/Atom feeds used as raw material for the daily post.
FEEDS = [
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
]

FALLBACK_IMAGE_PROMPT = "futuristic technology news studio with glowing holographic screens"
MAX_POST_CHARS = 900


@dataclass
class NewsPost:
    """A generated post: markdown text (with **bold**) and an English image prompt."""

    text: str
    image_prompt: str


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def fetch_headlines(limit_per_feed: int = 6, timeout: int = 10) -> List[str]:
    """Fetch recent headlines from RSS/Atom feeds. Failures are logged and skipped."""
    headlines: List[str] = []
    for url in FEEDS:
        try:
            response = requests.get(url, timeout=timeout, headers={"User-Agent": "news-bot/1.0"})
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except Exception as exc:  # network or parse problems must not break the post
            logger.warning("Could not read feed %s: %s", url, exc)
            continue

        count = 0
        for node in root.iter():
            if _local(node.tag) not in ("item", "entry"):
                continue
            title, summary = "", ""
            for child in node:
                name = _local(child.tag)
                if name == "title" and child.text:
                    title = child.text.strip()
                elif name in ("description", "summary") and child.text and not summary:
                    summary = re.sub(r"<[^>]+>", "", html.unescape(child.text)).strip()
            if title:
                headlines.append(f"- {title}" + (f": {summary[:200]}" if summary else ""))
                count += 1
            if count >= limit_per_feed:
                break
    return headlines


def build_prompt(headlines: List[str]) -> str:
    if headlines:
        source = "Here are today's fresh headlines:\n" + "\n".join(headlines)
    else:
        source = "No headlines are available; pick one notable, recent world or technology topic you know well."
    return f"""You are the editor of an Uzbek-language Telegram news channel about world and technology news.

{source}

Task: choose the single most interesting and important story and write ONE channel post about it.

Rules for the post text:
- Write in Uzbek (Latin script), journalistic and engaging tone, with a strong hook.
- Start with a headline wrapped in **double asterisks**.
- Wrap the 3-5 most important keywords inside the body in **double asterisks** too.
- Maximum {MAX_POST_CHARS} characters in total, including hashtags.
- Do not invent facts that are not supported by the headlines.
- Finish with 3-4 relevant hashtags on the last line (for example #yangiliklar #tech).
- Use no other markdown (no lists, no headings, no underscores).

Also write "image_prompt": one English sentence (max 40 words) describing a visual scene that illustrates the story.

Respond ONLY with JSON: {{"post": "...", "image_prompt": "..."}}"""


def parse_response(raw: str) -> NewsPost:
    """Parse Gemini's JSON answer, tolerating code fences or plain text."""
    cleaned = (raw or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        data = json.loads(cleaned)
        text = str(data.get("post", "")).strip()
        image_prompt = str(data.get("image_prompt", "")).strip() or FALLBACK_IMAGE_PROMPT
    except (json.JSONDecodeError, AttributeError):
        text, image_prompt = cleaned, FALLBACK_IMAGE_PROMPT
    if not text:
        raise ValueError("Gemini returned an empty post")
    return NewsPost(text=text, image_prompt=image_prompt)


def to_telegram_html(text: str) -> str:
    """Convert **bold** markdown into Telegram HTML, escaping everything else."""
    escaped = html.escape(text, quote=False)
    converted = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped, flags=re.DOTALL)
    return converted.replace("**", "").replace("*", "")


async def generate_news_post(settings: Settings) -> NewsPost:
    """Ask Gemini Flash for a fresh Uzbek news post plus an image prompt."""
    headlines = await asyncio.to_thread(fetch_headlines)
    logger.info("Collected %d headlines", len(headlines))

    # REST transport is more reliable than gRPC on some networks (gRPC caused 504 timeouts).
    genai.configure(api_key=settings.gemini_api_key, transport="rest")
    model = genai.GenerativeModel(
        settings.gemini_model,
        generation_config={"temperature": 0.8, "response_mime_type": "application/json"},
    )
    prompt = build_prompt(headlines)

    last_error: Exception = RuntimeError("Gemini request was not attempted")
    for attempt in range(1, 4):
        try:
            response = await asyncio.to_thread(
                model.generate_content, prompt, request_options={"timeout": 45}
            )
            return parse_response(response.text)
        except Exception as exc:
            last_error = exc
            logger.warning("Gemini attempt %d/3 failed: %s", attempt, exc)
            if "429" in str(exc) or "ResourceExhausted" in type(exc).__name__:
                break  # daily quota is used up; retrying would only waste more requests
            await asyncio.sleep(3 * attempt)
    raise last_error
