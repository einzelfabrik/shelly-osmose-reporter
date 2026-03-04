from __future__ import annotations

from typing import Any

from .base import Notifier
from .email_smtp import EmailConfig, EmailNotifier
from .telegram import TelegramConfig, TelegramNotifier
from .waha import WahaConfig, WahaNotifier


def build_notifiers(cfg: dict[str, Any]) -> list[Notifier]:
    notifiers: list[Notifier] = []
    channels = cfg.get("channels", {})

    if channels.get("waha", {}).get("enabled", False):
        w = channels["waha"]
        notifiers.append(
            WahaNotifier(
                WahaConfig(
                    base_url=w["base_url"],
                    api_key=w["api_key"],
                    chat_id=w["chat_id"],
                    session=w.get("session", "default"),
                    endpoint=w.get("endpoint", "/sendText"),
                    timeout_seconds=int(w.get("timeout_seconds", 10)),
                    retries=int(w.get("retries", 3)),
                    retry_delay_seconds=float(w.get("retry_delay_seconds", 2)),
                )
            )
        )

    if channels.get("telegram", {}).get("enabled", False):
        t = channels["telegram"]
        notifiers.append(
            TelegramNotifier(
                TelegramConfig(
                    bot_token=t["bot_token"],
                    chat_id=t["chat_id"],
                    timeout_seconds=int(t.get("timeout_seconds", 10)),
                )
            )
        )

    if channels.get("email", {}).get("enabled", False):
        e = channels["email"]
        recipients = e.get("recipients", [])
        if isinstance(recipients, str):
            recipients = [x.strip() for x in recipients.split(",") if x.strip()]
        notifiers.append(
            EmailNotifier(
                EmailConfig(
                    smtp_host=e["smtp_host"],
                    smtp_port=int(e.get("smtp_port", 587)),
                    username=e.get("username", ""),
                    password=e.get("password", ""),
                    sender=e["sender"],
                    recipients=recipients,
                    use_tls=bool(e.get("use_tls", True)),
                    subject_prefix=e.get("subject_prefix", "[Osmose]"),
                )
            )
        )

    return notifiers
