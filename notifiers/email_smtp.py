from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from .base import Notifier


@dataclass
class EmailConfig:
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    sender: str
    recipients: list[str]
    use_tls: bool = True
    subject_prefix: str = "[Osmose]"


class EmailNotifier(Notifier):
    def __init__(self, cfg: EmailConfig) -> None:
        self.cfg = cfg

    def send(self, message: str) -> None:
        mail = EmailMessage()
        mail["From"] = self.cfg.sender
        mail["To"] = ", ".join(self.cfg.recipients)
        mail["Subject"] = f"{self.cfg.subject_prefix} Tagesreport"
        mail.set_content(message)

        with smtplib.SMTP(self.cfg.smtp_host, self.cfg.smtp_port, timeout=15) as smtp:
            if self.cfg.use_tls:
                smtp.starttls()
            if self.cfg.username:
                smtp.login(self.cfg.username, self.cfg.password)
            smtp.send_message(mail)
