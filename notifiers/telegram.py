from __future__ import annotations

from dataclasses import dataclass

import requests

from .base import Notifier


@dataclass
class TelegramConfig:
    bot_token: str
    chat_id: str
    timeout_seconds: int = 10


class TelegramNotifier(Notifier):
    def __init__(self, cfg: TelegramConfig) -> None:
        self.cfg = cfg

    def send(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.cfg.bot_token}/sendMessage"
        payload = {
            "chat_id": self.cfg.chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=self.cfg.timeout_seconds)
        resp.raise_for_status()
