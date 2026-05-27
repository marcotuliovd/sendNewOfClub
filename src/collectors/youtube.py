from __future__ import annotations

import logging
from datetime import datetime, timezone

from googleapiclient.discovery import build

from src.config_loader import YouTubeChannel, YouTubeConfig
from src.models import RawItem

logger = logging.getLogger(__name__)


def _parse_published_at(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class YouTubeCollector:
    def __init__(self, api_key: str, config: YouTubeConfig):
        self._api_key = api_key
        self._config = config
        self._youtube = build("youtube", "v3", developerKey=api_key)

    def collect(self, since: datetime) -> list[RawItem]:
        items: list[RawItem] = []
        for channel in self._config.channels:
            try:
                channel_items = self._fetch_channel_videos(channel, since)
                logger.info(
                    "Collected %s YouTube items from %s",
                    len(channel_items),
                    channel.name,
                )
                items.extend(channel_items)
            except Exception:
                logger.exception("Failed to collect YouTube channel %s", channel.name)
        return items

    def _resolve_channel_id(self, channel: YouTubeChannel) -> str | None:
        if channel.id:
            return channel.id

        if not channel.handle:
            return None

        handle = channel.handle.lstrip("@")
        response = (
            self._youtube.channels()
            .list(part="id", forHandle=handle)
            .execute()
        )
        items = response.get("items", [])
        if not items:
            logger.warning(
                "YouTube channel not found by handle: %s (%s)",
                channel.name,
                channel.handle,
            )
            return None

        return items[0]["id"]

    def _fetch_channel_videos(
        self, channel: YouTubeChannel, since: datetime
    ) -> list[RawItem]:
        channel_id = self._resolve_channel_id(channel)
        if not channel_id:
            return []

        channel_response = (
            self._youtube.channels()
            .list(part="contentDetails", id=channel_id)
            .execute()
        )
        channel_items = channel_response.get("items", [])
        if not channel_items:
            logger.warning("YouTube channel not found: %s (%s)", channel.name, channel_id)
            return []

        uploads_playlist_id = channel_items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        playlist_response = (
            self._youtube.playlistItems()
            .list(
                part="snippet,contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=10,
            )
            .execute()
        )

        recent_entries = []
        for entry in playlist_response.get("items", []):
            snippet = entry["snippet"]
            published_at = _parse_published_at(snippet["publishedAt"])
            if published_at >= since:
                recent_entries.append(entry)

        if not recent_entries:
            return []

        video_ids = [entry["contentDetails"]["videoId"] for entry in recent_entries]
        videos_response = (
            self._youtube.videos()
            .list(part="snippet", id=",".join(video_ids))
            .execute()
        )

        items: list[RawItem] = []
        for video in videos_response.get("items", []):
            snippet = video["snippet"]
            title = snippet.get("title", "")
            description = snippet.get("description", "")
            published_at = _parse_published_at(snippet["publishedAt"])
            video_id = video["id"]

            items.append(
                RawItem(
                    source="youtube",
                    id=video_id,
                    title=title,
                    body=description,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    published_at=published_at,
                    metadata={
                        "channel_name": channel.name,
                        "channel_id": channel_id,
                        "channel_handle": channel.handle,
                    },
                )
            )

        return items
