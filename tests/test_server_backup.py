"""GET /api/admin/backup: das Volume als Zip, nur mit dem Admin-Token.

Das Zip traegt jede vorhandene Datei einmal, die SQLite-Buecher als
konsistente Kopie ueber die Backup-API, dazu ein Manifest mit Groesse und
SHA-256 je Datei. Ohne Token 403 wie jeder Schreibpfad des Copy-Desks.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from api import server


class BackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "copy_trading.sqlite"
        con = sqlite3.connect(self.db)
        con.execute("create table trades (id integer primary key, note text)")
        con.executemany("insert into trades (note) values (?)", [("a",), ("b",), ("c",)])
        con.commit()
        con.close()
        self.settings = self.tmp / "copy_settings.json"
        self.settings.write_text('{"scale": 1}', encoding="utf-8")
        # Entity-Graph und Flag-Log fehlen absichtlich: nicht vorhandene
        # Dateien duerfen weder scheitern noch im Zip auftauchen.
        self.patches = [
            mock.patch.object(server, "COPY_DB_PATH", self.db),
            mock.patch.object(server, "COPY_SETTINGS_PATH", self.settings),
            mock.patch.object(server, "COPY_STATUS_PATH", self.tmp / "copy_trader_status.json"),
            mock.patch.dict(os.environ, {
                "COPY_ADMIN_TOKEN": "geheim-123",
                "ENTITY_GRAPH_PATH": str(self.tmp / "fehlt.sqlite"),
                "RISK_LOG_DIR": str(self.tmp / "fehlt"),
            }),
        ]
        for p in self.patches:
            p.start()
        # Kein ``with``: der Lifespan wuerde die Hintergrund-Threads starten.
        self.client = TestClient(server.app)

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ohne_token_verweigert(self) -> None:
        r = self.client.get("/api/admin/backup")
        self.assertEqual(r.status_code, 403)
        r = self.client.get("/api/admin/backup", headers={"X-Admin-Token": "falsch"})
        self.assertEqual(r.status_code, 403)

    def test_mit_token_ein_zip_mit_manifest(self) -> None:
        r = self.client.get("/api/admin/backup", headers={"X-Admin-Token": "geheim-123"})
        self.assertEqual(r.status_code, 200, r.text[:200])
        self.assertEqual(r.headers["content-type"], "application/zip")
        self.assertIn("marketintel-volume-", r.headers.get("content-disposition", ""))
        # Schutzheader der API gelten auch hier.
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")

        zf = zipfile.ZipFile(io.BytesIO(r.content))
        self.assertIsNone(zf.testzip())
        self.assertEqual(sorted(zf.namelist()), ["copy_settings.json", "copy_trading.sqlite", "manifest.json"])

        manifest = json.loads(zf.read("manifest.json"))
        by_name = {f["name"]: f for f in manifest["files"]}
        self.assertEqual(set(by_name), {"copy_settings.json", "copy_trading.sqlite"})
        for name, eintrag in by_name.items():
            daten = zf.read(name)
            self.assertEqual(eintrag["bytes"], len(daten))
            self.assertEqual(eintrag["sha256"], hashlib.sha256(daten).hexdigest())
        self.assertTrue(manifest["created_utc"])

        # Die SQLite-Kopie ist eine lesbare Datenbank mit denselben Zeilen.
        kopie = self.tmp / "kopie.sqlite"
        kopie.write_bytes(zf.read("copy_trading.sqlite"))
        con = sqlite3.connect(kopie)
        self.assertEqual(con.execute("select count(*) from trades").fetchone()[0], 3)
        con.close()

    def test_ohne_dateien_404(self) -> None:
        self.db.unlink()
        self.settings.unlink()
        r = self.client.get("/api/admin/backup", headers={"X-Admin-Token": "geheim-123"})
        self.assertEqual(r.status_code, 404)

    def test_gleiche_dateinamen_bleiben_beide_erhalten(self) -> None:
        # Zwei Kandidaten mit demselben Namen in verschiedenen Ordnern.
        anderer = self.tmp / "graph"
        anderer.mkdir()
        (anderer / "copy_settings.json").write_text("{}", encoding="utf-8")
        ziel = self.tmp / "out.zip"
        manifest = server.backup_zip_schreiben(ziel, [self.settings, anderer / "copy_settings.json"])
        namen = [f["name"] for f in manifest["files"]]
        self.assertEqual(namen, ["copy_settings.json", "graph__copy_settings.json"])
        self.assertEqual(sorted(zipfile.ZipFile(ziel).namelist()), sorted(namen + ["manifest.json"]))


if __name__ == "__main__":
    unittest.main()
