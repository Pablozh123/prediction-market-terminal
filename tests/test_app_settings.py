import json
import tempfile
import unittest
from pathlib import Path

from app import app_settings as cfg
from app import notify


class AppSettingsTests(unittest.TestCase):
    def test_defaults_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = cfg.load_settings(Path(tmp) / "missing.json")
        self.assertEqual(settings, cfg.DEFAULTS)

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            cfg.save_settings({"market_sample": 100, "alerts_enabled": True, "telegram_chat_id": "42"}, path)
            settings = cfg.load_settings(path)
        self.assertEqual(settings["market_sample"], 100)
        self.assertTrue(settings["alerts_enabled"])
        self.assertEqual(settings["telegram_chat_id"], "42")
        self.assertEqual(settings["trade_sample"], cfg.DEFAULTS["trade_sample"])

    def test_bad_values_reset_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({"market_sample": "not-a-number", "unknown_key": 1}), encoding="utf-8")
            settings = cfg.load_settings(path)
        self.assertEqual(settings["market_sample"], cfg.DEFAULTS["market_sample"])
        self.assertNotIn("unknown_key", settings)

    def test_corrupt_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text("{broken", encoding="utf-8")
            settings = cfg.load_settings(path)
        self.assertEqual(settings, cfg.DEFAULTS)


class NotifyTests(unittest.TestCase):
    def test_missing_credentials_fail_fast_without_network(self):
        ok, detail = notify.send_telegram("", "", "hello")
        self.assertFalse(ok)
        self.assertIn("missing", detail)


if __name__ == "__main__":
    unittest.main()
