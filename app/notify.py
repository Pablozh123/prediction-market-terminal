"""Outbound notification helpers (Telegram). Streamlit-free."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

TELEGRAM_API = "https://api.telegram.org"


def send_telegram(token: str, chat_id: str, text: str, timeout: int = 15) -> tuple[bool, str]:
    """Send a Telegram message. Returns (ok, detail)."""

    token = str(token or "").strip()
    chat_id = str(chat_id or "").strip()
    if not token or not chat_id:
        return False, "Telegram bot token or chat id missing."
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": "true"}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        if body.get("ok"):
            return True, "sent"
        return False, str(body.get("description", "unknown Telegram error"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("description", str(exc))
        except Exception:
            detail = str(exc)
        return False, f"HTTP {exc.code}: {detail}"
    except Exception as exc:
        return False, str(exc)
