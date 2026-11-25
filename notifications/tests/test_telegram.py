from unittest.mock import patch

import requests

from django.test import SimpleTestCase, override_settings

from notifications.telegram import (
    TelegramNotificationError,
    TelegramTemporaryError,
    send_telegram_message,
)


@override_settings(
    TELEGRAM_BOT_TOKEN="test-token",
    TELEGRAM_CHAT_ID="-100123456789",
)
class TelegramClientTests(SimpleTestCase):
    @patch("notifications.telegram.requests.post")
    def test_send_message_successfully(self, mock_post):
        response = mock_post.return_value
        response.status_code = 200
        response.json.return_value = {"ok": True}

        result = send_telegram_message("Test message")

        self.assertTrue(result)
        mock_post.assert_called_once_with(
            "https://api.telegram.org/bottest-token/sendMessage",
            json={
                "chat_id": "-100123456789",
                "text": "Test message",
            },
            timeout=10,
        )

    @override_settings(TELEGRAM_BOT_TOKEN="")
    @patch("notifications.telegram.requests.post")
    def test_missing_bot_token(self, mock_post):
        result = send_telegram_message("Test message")

        self.assertFalse(result)
        mock_post.assert_not_called()

    @override_settings(TELEGRAM_CHAT_ID="")
    @patch("notifications.telegram.requests.post")
    def test_missing_chat_id(self, mock_post):
        result = send_telegram_message("Test message")

        self.assertFalse(result)
        mock_post.assert_not_called()

    @patch("notifications.telegram.requests.post")
    def test_network_error(self, mock_post):
        mock_post.side_effect = requests.RequestException(
            "Connection failed"
        )

        with self.assertRaises(TelegramTemporaryError):
            send_telegram_message("Test message")

    @patch("notifications.telegram.requests.post")
    def test_rate_limit_error(self, mock_post):
        mock_post.return_value.status_code = 429

        with self.assertRaises(TelegramTemporaryError):
            send_telegram_message("Test message")

    @patch("notifications.telegram.requests.post")
    def test_server_error(self, mock_post):
        mock_post.return_value.status_code = 503

        with self.assertRaises(TelegramTemporaryError):
            send_telegram_message("Test message")

    @patch("notifications.telegram.requests.post")
    def test_client_error(self, mock_post):
        mock_post.return_value.status_code = 400

        with self.assertRaises(TelegramNotificationError):
            send_telegram_message("Test message")

    @patch("notifications.telegram.requests.post")
    def test_invalid_json_response(self, mock_post):
        response = mock_post.return_value
        response.status_code = 200
        response.json.side_effect = ValueError("Invalid JSON")

        with self.assertRaises(TelegramTemporaryError):
            send_telegram_message("Test message")

    @patch("notifications.telegram.requests.post")
    def test_telegram_rejects_message(self, mock_post):
        response = mock_post.return_value
        response.status_code = 200
        response.json.return_value = {"ok": False}

        with self.assertRaises(TelegramNotificationError):
            send_telegram_message("Test message")
