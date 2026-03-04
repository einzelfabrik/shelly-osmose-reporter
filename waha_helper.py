import base64
import mimetypes
import os
import time
from typing import Dict, Optional

import requests


def _get_headers(api_key: Optional[str]) -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key
    return headers


def send_whatsapp_message(
    base_url: str,
    api_key: Optional[str],
    message: str,
    empfaenger: str,
    session: str = "default",
    endpoint: str = "/sendText",
    retries: int = 3,
    retry_delay_seconds: float = 2.0,
    timeout_seconds: int = 10,
) -> None:
    """Sendet eine WhatsApp-Textnachricht über den WAHA-Server."""
    url = f"{base_url.rstrip('/')}{endpoint}"
    payload = {"chatId": empfaenger, "text": message, "session": session}
    headers = _get_headers(api_key)
    headers["Content-Type"] = "application/json"

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout_seconds)
            response.raise_for_status()
            print(f"[WhatsApp] Text gesendet (Session '{session}', Versuch {attempt}/{retries}).")
            return
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            print(f"[WhatsApp] Sendeversuch {attempt}/{retries} fehlgeschlagen: {exc}")
            if attempt < retries:
                time.sleep(retry_delay_seconds * attempt)

    print("[WhatsApp] Fehler beim Senden des Textes über WAHA.")
    if hasattr(last_exc, "response") and last_exc.response is not None:
        print(f"[WhatsApp] Server-Antwort: {last_exc.response.text}")


def send_whatsapp_file(
    base_url: str,
    api_key: Optional[str],
    file_path: str,
    empfaenger: str,
    session: str = "default",
    caption: str = "",
    retries: int = 3,
    retry_delay_seconds: float = 2.0,
    timeout_seconds: int = 30,
) -> None:
    """Sendet eine Datei (Bild, PDF, etc.) über den WAHA-Server."""
    if not os.path.exists(file_path):
        print(f"[WhatsApp] Fehler: Datei nicht gefunden: {file_path}")
        return

    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = "application/octet-stream"
    endpoint = "/sendImage" if mime_type.startswith("image/") else "/sendFile"
    url = f"{base_url.rstrip('/')}{endpoint}"
    filename = os.path.basename(file_path)
    headers = _get_headers(api_key)
    headers["Content-Type"] = "application/json"

    with open(file_path, "rb") as file_handle:
        file_data = base64.b64encode(file_handle.read()).decode("utf-8")

    payload = {
        "chatId": empfaenger,
        "session": session,
        "caption": caption,
        "file": {"mimetype": mime_type, "filename": filename, "data": file_data},
    }

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout_seconds)
            response.raise_for_status()
            print(
                f"[WhatsApp] Datei '{filename}' gesendet "
                f"(Session '{session}', Versuch {attempt}/{retries})."
            )
            return
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            print(f"[WhatsApp] Dateiversand Versuch {attempt}/{retries} fehlgeschlagen: {exc}")
            if attempt < retries:
                time.sleep(retry_delay_seconds * attempt)

    print("[WhatsApp] Fehler beim Dateiversand über WAHA.")
    if hasattr(last_exc, "response") and last_exc.response is not None:
        print(f"[WhatsApp] Server-Antwort: {last_exc.response.text}")
