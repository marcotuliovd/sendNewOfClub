from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.ai.summarizer import summarize
from src.collectors.twitter import TwitterCollector
from src.collectors.youtube import YouTubeCollector
from src.config_loader import load_config
from src.delivery.console import ConsoleDelivery
from src.storage.dedup import DedupStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "sources.yaml"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "state.db"


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


async def run(config_path: Path = DEFAULT_CONFIG_PATH, force: bool = False) -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    config = load_config(config_path)

    youtube_since = datetime.now(timezone.utc) - timedelta(
        hours=config.youtube.lookback_hours
    )
    twitter_since = datetime.now(timezone.utc) - timedelta(
        hours=config.twitter.lookback_hours
    )

    logger.info("Collecting YouTube content since %s", youtube_since.isoformat())
    youtube_collector = YouTubeCollector(
        api_key=_require_env("YOUTUBE_API_KEY"),
        config=config.youtube,
    )
    yt_items = youtube_collector.collect(youtube_since)
    logger.info("Collected %s YouTube items", len(yt_items))

    logger.info("Collecting X/Twitter content since %s", twitter_since.isoformat())
    twitter_collector = TwitterCollector(config=config.twitter)
    x_items = await twitter_collector.collect(twitter_since)
    logger.info("Collected %s X/Twitter items", len(x_items))

    dedup = DedupStore(DEFAULT_DB_PATH)
    collected_items = yt_items + x_items
    all_items = collected_items if force else dedup.filter_new(collected_items)
    if force:
        logger.info(
            "Force mode enabled: summarizing %s collected items without dedup filter",
            len(all_items),
        )
    else:
        logger.info("%s new items after deduplication", len(all_items))

    delivery = ConsoleDelivery()
    if not all_items:
        delivery.send("Nenhuma novidade do Galo hoje. 💤")
        return

    logger.info("Summarizing %s items with Gemini", len(all_items))
    report = summarize(all_items, api_key=_require_env("GEMINI_API_KEY"))

    delivery.send(report)
    reported_items = [item for item in all_items if item.url in report]
    if reported_items:
        dedup.mark_seen(reported_items)
        logger.info(
            "Report delivered and %s/%s reported items marked as seen",
            len(reported_items),
            len(all_items),
        )
    else:
        logger.warning("Report delivered with no source URLs; no items marked as seen")


def main() -> None:
    config_path = DEFAULT_CONFIG_PATH
    args = sys.argv[1:]
    force = "--force" in args
    config_args = [arg for arg in args if arg != "--force"]
    if config_args:
        config_path = Path(config_args[0])

    try:
        asyncio.run(run(config_path=config_path, force=force))
    except Exception:
        logger.exception("Pipeline failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
