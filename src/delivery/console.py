from __future__ import annotations

from src.delivery.base import BaseDelivery


class ConsoleDelivery(BaseDelivery):
    def send(self, message: str) -> None:
        print("\n" + "=" * 50)
        print("RELATÓRIO WHATSAPP (simulado)")
        print("=" * 50)
        print(message)
        print("=" * 50 + "\n")
