import requests

from django.conf import settings


class TelegramNotificationError(Exception):
    """Raised when Telegram rejects a notification."""


class TelegramTemporaryError(TelegramNotificationError):
    """Raised when sending a notification can be retried."""


def send_telegram_message(text: str) -> bool:
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        response = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise TelegramTemporaryError(
            "Could not connect to Telegram API."
        ) from exc

    if response.status_code == 429 or response.status_code >= 500:
        raise TelegramTemporaryError(
            "Telegram API is temporarily unavailable."
        )

    if response.status_code >= 400:
        raise TelegramNotificationError(
            "Telegram API rejected the message."
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise TelegramTemporaryError(
            "Invalid response from Telegram API."
        ) from exc

    if not payload.get("ok"):
        raise TelegramNotificationError(
            "Telegram API did not accept the message."
        )

    return True
