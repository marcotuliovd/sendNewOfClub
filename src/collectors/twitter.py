from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from src.config_loader import TwitterConfig, TwitterProfile
from src.models import RawItem

logger = logging.getLogger(__name__)

SYNDICATION_URL = (
    "https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"
)
MAX_SYNDICATION_RETRIES = 3
RETRY_BACKOFF_SECONDS = 15
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://publish.twitter.com",
}


class TwitterCollectionSkipped(Exception):
    """Expected X/Twitter collection failure, usually rate limiting."""


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_twitter_date(value: str) -> datetime:
    try:
        return _ensure_aware(datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y"))
    except ValueError:
        return _ensure_aware(parsedate_to_datetime(value))


def _load_cookie_header(cookies_path: str | None) -> str | None:
    if not cookies_path:
        return None

    path = Path(cookies_path)
    if not path.is_file():
        logger.warning("Twitter cookies file not found: %s", path)
        return None

    with path.open(encoding="utf-8") as f:
        raw = json.load(f)

    cookies: dict[str, str] = {}
    if isinstance(raw, dict):
        cookies = {str(k): str(v) for k, v in raw.items()}
    elif isinstance(raw, list):
        for item in raw:
            name = item.get("name")
            value = item.get("value")
            if name and value is not None:
                cookies[str(name)] = str(value)

    if not cookies:
        logger.warning("Twitter cookies file is empty or invalid: %s", path)
        return None

    parts = ["dnt=1"]
    parts.extend(f"{name}={value}" for name, value in cookies.items())
    return "; ".join(parts)


def _extract_timeline_entries(html: str) -> list[dict]:
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        raise ValueError("Timeline page did not include __NEXT_DATA__")

    payload = json.loads(match.group(1))
    entries = payload.get("props", {}).get("pageProps", {}).get("timeline", {}).get(
        "entries", []
    )
    if not isinstance(entries, list):
        raise ValueError("Unexpected syndication timeline payload")
    return entries


class TwitterCollector:
    def __init__(self, config: TwitterConfig, cookies_path: str | None = None):
        self._config = config
        self._cookie_header = _load_cookie_header(
            cookies_path or os.environ.get("TWITTER_COOKIES_PATH")
        )
        if self._cookie_header:
            logger.info("Twitter collector using cookies from TWITTER_COOKIES_PATH")
        else:
            logger.info(
                "Twitter collector running without cookies "
                "(set TWITTER_COOKIES_PATH if requests fail)"
            )

    async def collect(self, since: datetime) -> list[RawItem]:
        since = _ensure_aware(since)
        items: list[RawItem] = []

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            for profile in self._config.profiles:
                try:
                    profile_items = await self._fetch_user_tweets(
                        client, profile, since
                    )
                    items.extend(profile_items)
                except TwitterCollectionSkipped as exc:
                    logger.warning("Skipping tweets for @%s: %s", profile.username, exc)
                except Exception:
                    logger.exception("Failed to collect tweets for @%s", profile.username)

        return items

    async def _fetch_user_tweets(
        self,
        client: httpx.AsyncClient,
        profile: TwitterProfile,
        since: datetime,
    ) -> list[RawItem]:
        url = SYNDICATION_URL.format(username=profile.username)
        headers = dict(DEFAULT_HEADERS)
        if self._cookie_header:
            headers["Cookie"] = self._cookie_header

        last_error: Exception | None = None
        max_attempts = MAX_SYNDICATION_RETRIES if self._cookie_header else 1
        for attempt in range(max_attempts):
            response = await client.get(url, headers=headers)
            if response.status_code == 429:
                last_error = TwitterCollectionSkipped(
                    "X syndication rate limit exceeded — wait a few minutes or set "
                    "TWITTER_COOKIES_PATH with browser cookies"
                )
                if attempt == max_attempts - 1:
                    raise last_error
                wait = RETRY_BACKOFF_SECONDS * (attempt + 1)
                logger.warning(
                    "Rate limited fetching @%s (attempt %s/%s). Retrying in %ss.",
                    profile.username,
                    attempt + 1,
                    max_attempts,
                    wait,
                )
                await asyncio.sleep(wait)
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise TwitterCollectionSkipped(
                    f"Failed to fetch timeline for @{profile.username}: HTTP {exc.response.status_code}"
                ) from exc
            break
        else:
            raise last_error or RuntimeError(
                f"Failed to fetch timeline for @{profile.username}"
            )

        entries = _extract_timeline_entries(response.text)
        items: list[RawItem] = []

        for entry in entries:
            tweet = (entry.get("content") or {}).get("tweet")
            if not tweet:
                continue

            text = tweet.get("full_text") or tweet.get("text") or ""
            if text.startswith("RT @"):
                continue

            tweet_id = str(tweet.get("id_str") or tweet.get("id") or "")
            if not tweet_id:
                continue

            created_at = _parse_twitter_date(tweet["created_at"])
            if created_at < since:
                continue

            permalink = tweet.get("permalink") or f"/{profile.username}/status/{tweet_id}"
            if permalink.startswith("/"):
                tweet_url = f"https://x.com{permalink}"
            else:
                tweet_url = permalink

            items.append(
                RawItem(
                    source="twitter",
                    id=tweet_id,
                    title=f"@{profile.username}",
                    body=text,
                    url=tweet_url,
                    published_at=created_at,
                    metadata={
                        "display_name": profile.display_name,
                        "username": profile.username,
                    },
                )
            )

        logger.info("Collected %s tweets for @%s", len(items), profile.username)
        return items
