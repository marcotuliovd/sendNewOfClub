from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class YouTubeChannel:
    name: str
    handle: str | None = None
    id: str | None = None


@dataclass
class YouTubeConfig:
    lookback_hours: int
    channels: list[YouTubeChannel]


@dataclass
class TwitterProfile:
    username: str
    display_name: str


@dataclass
class TwitterConfig:
    lookback_hours: int
    profiles: list[TwitterProfile]


@dataclass
class AppConfig:
    youtube: YouTubeConfig
    twitter: TwitterConfig


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    youtube_raw = raw.get("youtube", {})
    twitter_raw = raw.get("twitter", {})

    youtube_channels = []
    for ch in youtube_raw.get("channels", []):
        if not ch.get("id") and not ch.get("handle"):
            raise ValueError(
                f"YouTube channel '{ch.get('name', '?')}' precisa de 'id' ou 'handle'"
            )
        youtube_channels.append(
            YouTubeChannel(
                name=ch["name"],
                handle=ch.get("handle"),
                id=ch.get("id"),
            )
        )

    twitter_profiles = [
        TwitterProfile(
            username=profile["username"],
            display_name=profile["display_name"],
        )
        for profile in twitter_raw.get("profiles", [])
    ]

    return AppConfig(
        youtube=YouTubeConfig(
            lookback_hours=youtube_raw.get("lookback_hours", 24),
            channels=youtube_channels,
        ),
        twitter=TwitterConfig(
            lookback_hours=twitter_raw.get("lookback_hours", 24),
            profiles=twitter_profiles,
        ),
    )
