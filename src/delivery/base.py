from __future__ import annotations

from abc import ABC, abstractmethod


class BaseDelivery(ABC):
    @abstractmethod
    def send(self, message: str) -> None:
        """Deliver the final report message."""
