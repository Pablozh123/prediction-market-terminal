"""Tests for app/notify.py — outbound Telegram delivery.

Nothing here touches the network: the transport is patched, and what is
asserted is the contract around it. A notifier that raises takes the alert
scanner down with it, so every failure has to come back as a value.
"""

from __future__ import annotations

import io
import json
import unittest
import urllib.error
from unittest import mock

from app import notify


class _Antwort(io.BytesIO):
    """Minimal stand-in for the object urlopen returns as a context manager."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _ok_antwort(payload: dict) -> _Antwort:
    return _Antwort(json.dumps(payload).encode("utf-8"))


class CredentialGuardTests(unittest.TestCase):
    def test_missing_credentials_never_reach_the_network(self) -> None:
        with mock.patch("urllib.request.urlopen") as urlopen:
            for token, chat in (("", "123"), ("t", ""), ("", ""), (None, None)):
                with self.subTest(token=token, chat=chat):
                    ok, detail = notify.send_telegram(token, chat, "hi")
                    self.assertFalse(ok)
                    self.assertIn("missing", detail)
            urlopen.assert_not_called()


class SendTests(unittest.TestCase):
    def test_success_reports_sent(self) -> None:
        with mock.patch("urllib.request.urlopen", return_value=_ok_antwort({"ok": True})):
            self.assertEqual(notify.send_telegram("tok", "42", "hello"), (True, "sent"))

    def test_api_level_refusal_is_a_value_not_an_exception(self) -> None:
        antwort = _ok_antwort({"ok": False, "description": "chat not found"})
        with mock.patch("urllib.request.urlopen", return_value=antwort):
            ok, detail = notify.send_telegram("tok", "42", "hello")
        self.assertFalse(ok)
        self.assertEqual(detail, "chat not found")

    def test_the_request_carries_the_chat_and_the_text(self) -> None:
        aufrufe = []

        def _fake(request, timeout=None):
            aufrufe.append(request)
            return _ok_antwort({"ok": True})

        with mock.patch("urllib.request.urlopen", side_effect=_fake):
            notify.send_telegram("tok", "42", "hello")
        request = aufrufe[0]
        self.assertIn("/bottok/sendMessage", request.full_url)
        self.assertIn(b"chat_id=42", request.data)
        self.assertIn(b"text=hello", request.data)

    def test_long_text_is_cut_to_the_api_limit(self) -> None:
        aufrufe = []

        def _fake(request, timeout=None):
            aufrufe.append(request)
            return _ok_antwort({"ok": True})

        with mock.patch("urllib.request.urlopen", side_effect=_fake):
            notify.send_telegram("tok", "42", "x" * 9000)
        # 4000 x's survive; anything longer is rejected by the API outright.
        self.assertIn(b"text=" + b"x" * 4000 + b"&", aufrufe[0].data + b"&")
        self.assertNotIn(b"x" * 4001, aufrufe[0].data)


class FailureTests(unittest.TestCase):
    def test_http_error_reports_the_code_and_the_reason(self) -> None:
        fehler = urllib.error.HTTPError(
            "url", 429, "Too Many Requests", {},
            io.BytesIO(json.dumps({"description": "retry later"}).encode("utf-8")))
        with mock.patch("urllib.request.urlopen", side_effect=fehler):
            ok, detail = notify.send_telegram("tok", "42", "hello")
        self.assertFalse(ok)
        self.assertIn("429", detail)
        self.assertIn("retry later", detail)

    def test_http_error_with_an_unreadable_body_still_returns(self) -> None:
        fehler = urllib.error.HTTPError("url", 500, "Server Error", {}, io.BytesIO(b"not json"))
        with mock.patch("urllib.request.urlopen", side_effect=fehler):
            ok, detail = notify.send_telegram("tok", "42", "hello")
        self.assertFalse(ok)
        self.assertIn("500", detail)

    def test_a_dead_socket_comes_back_as_a_value(self) -> None:
        # The alert scanner loops over this; an exception here would end the run.
        with mock.patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            ok, detail = notify.send_telegram("tok", "42", "hello")
        self.assertFalse(ok)
        self.assertIn("connection refused", detail)


if __name__ == "__main__":
    unittest.main()
