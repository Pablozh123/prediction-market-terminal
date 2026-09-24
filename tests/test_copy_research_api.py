import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from api import server
from app import copy_admin as ca, copy_intelligence as ci


class ResearchApiTests(unittest.TestCase):
    def test_lightweight_route_obeys_privacy_and_never_loads_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'copy.sqlite'
            wallet = '0x' + 'a' * 40
            ci.import_watchlist([{'wallet': wallet, 'sources': ['https://x.com/example/status/123']}], db)
            with patch.object(server, 'COPY_DB_PATH', db), \
                 patch.object(server, 'COPY_DESK_PRIVATE', True), \
                 patch.object(server, '_copy_write_access', return_value=ca.write_access('remote', None, 'token')), \
                 patch.object(ci, 'refresh_async'), \
                 patch('src.copy_trading.get_paper_orders', side_effect=AssertionError('heavy ledger read')):
                client = TestClient(server.app)
                self.assertEqual(client.get('/api/copy/research').status_code, 403)
                with patch.object(server, '_copy_write_access', return_value=ca.write_access('127.0.0.1', None, '')):
                    response = client.get('/api/copy/research')
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertTrue(payload['research_only'])
                self.assertIn(wallet, payload['intelligence']['watchlist'])
                self.assertTrue(any(r['wallet'] == wallet for r in payload['traders']))


if __name__ == '__main__':
    unittest.main()
