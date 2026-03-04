from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from .base import Notifier


@dataclass
class WahaConfig:
    base_url: str
    api_key: str
    chat_id: str
    session: str = "default"
    endpoint: str = "/sendText"
    timeout_seconds: int = 10
    retries: int = 3
    retry_delay_seconds: float = 2.0


class WahaNotifier(Notifier):
    def __init__(self, cfg: WahaConfig) -> None:
        self.cfg = cfg

    def send(self, message: str) -> None:
        url = f"{self.cfg.base_url.rstrip('/')}{self.cfg.endpoint}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Api-Key": self.cfg.api_key,
        }
        payload = {"chatId": self.cfg.chat_id, "text": message, "session": self.cfg.session}

        last_exc = None
        for attempt in range(1, self.cfg.retries + 1):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=self.cfg.timeout_seconds)
                resp.raise_for_status()
                return
            except requests.RequestException as exc:  # pragma: no cover - network path
                last_exc = exc
                if attempt < self.cfg.retries:
                    time.sleep(self.cfg.retry_delay_seconds * attempt)
        raise RuntimeError(f"WAHA send failed after retries: {last_exc}")
