from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawItem:
    source: str
    id: str
    title: str
    body: str
    url: str
    published_at: datetime
    metadata: dict = field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        return f"{self.source}:{self.id}"
