from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.models import RawItem


class BaseCollector(ABC):
    @abstractmethod
    def collect(self, since: datetime) -> list[RawItem]:
        """Collect raw items published on or after `since`."""
