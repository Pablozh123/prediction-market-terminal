import base64
import tempfile
import unittest
from pathlib import Path

from app import kalshi_auth as ka


def throwaway_key(directory: Path, name: str = "test_key.pem") -> Path:
    """An ephemeral RSA key generated for this test only. Never a real secret."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = directory / name
    path.write_bytes(pem)
    return path


class RequestGuardTests(unittest.TestCase):
    """The point of the module: a read key cannot become a trading key."""

    def test_get_on_a_market_path_is_allowed(self):
        ka.check_request("GET", "/trade-api/v2/markets")

    def test_lowercase_get_is_accepted(self):
        ka.check_request("get", "/trade-api/v2/markets")

    def test_post_is_refused(self):
        with self.assertRaises(ka.ForbiddenRequest):
            ka.check_request("POST", "/trade-api/v2/markets")

    def test_delete_is_refused(self):
        with self.assertRaises(ka.ForbiddenRequest):
            ka.check_request("DELETE", "/trade-api/v2/markets")

    def test_an_empty_method_is_refused(self):
        with self.assertRaises(ka.ForbiddenRequest):
            ka.check_request("", "/trade-api/v2/markets")

    def test_the_order_path_is_refused_even_as_a_get(self):
        with self.assertRaises(ka.ForbiddenRequest):
            ka.check_request("GET", "/trade-api/v2/portfolio/orders")

    def test_every_blocked_fragment_is_actually_blocked(self):
        for fragment in ka.BLOCKED_PATH_FRAGMENTS:
            with self.assertRaises(ka.ForbiddenRequest, msg=fragment):
                ka.check_request("GET", f"/trade-api/v2{fragment}")

    def test_the_block_is_case_insensitive(self):
        with self.assertRaises(ka.ForbiddenRequest):
            ka.check_request("GET", "/trade-api/v2/PORTFOLIO/Orders")

    def test_signing_a_blocked_request_never_happens(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = throwaway_key(Path(tmp))
            creds = ka.load_credentials("kid", path, allow_in_repo=True)
            with self.assertRaises(ka.ForbiddenRequest):
                ka.sign(creds, 1, "POST", "/trade-api/v2/portfolio/orders")

    def test_auth_headers_are_refused_for_a_blocked_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = throwaway_key(Path(tmp))
            creds = ka.load_credentials("kid", path, allow_in_repo=True)
            with self.assertRaises(ka.ForbiddenRequest):
                ka.auth_headers(creds, "POST", "/trade-api/v2/portfolio/orders", 1)


class StorageGuardTests(unittest.TestCase):
    def test_a_key_inside_the_repository_is_refused(self):
        # Das Repo ist oeffentlich; eine gitignore-Regel schuetzt nur gegen
        # Versehen, nicht gegen `git add -f` oder ein Zip des Ordners.
        inside = ka.REPO_ROOT / "data"
        inside.mkdir(exist_ok=True)
        path = throwaway_key(inside, "pruef_schluessel.pem")
        try:
            with self.assertRaises(ka.CredentialError) as ctx:
                ka.load_credentials("kid", path)
            self.assertIn("Repository", str(ctx.exception))
        finally:
            path.unlink(missing_ok=True)

    def test_a_key_outside_the_repository_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = throwaway_key(Path(tmp))
            creds = ka.load_credentials("kid", path)
            self.assertEqual(creds.key_id, "kid")

    def test_a_missing_file_is_reported_clearly(self):
        with self.assertRaises(ka.CredentialError) as ctx:
            ka.load_credentials("kid", "C:/gibt/es/nicht.pem")
        self.assertIn("nicht gefunden", str(ctx.exception))

    def test_a_missing_key_id_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = throwaway_key(Path(tmp))
            with self.assertRaises(ka.CredentialError) as ctx:
                ka.load_credentials("", path)
            self.assertIn(ka.KEY_ID_ENV, str(ctx.exception))

    def test_a_missing_path_is_reported(self):
        with self.assertRaises(ka.CredentialError) as ctx:
            ka.load_credentials("kid", "")
        self.assertIn(ka.PRIVATE_KEY_PATH_ENV, str(ctx.exception))

    def test_a_file_that_is_not_a_pem_is_refused_without_echoing_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kaputt.pem"
            path.write_text("GEHEIMES-MATERIAL-DAS-NICHT-AUFTAUCHEN-DARF",
                            encoding="utf-8")
            with self.assertRaises(ka.CredentialError) as ctx:
                ka.load_credentials("kid", path)
            self.assertNotIn("GEHEIMES-MATERIAL", str(ctx.exception))

    def test_the_credential_repr_hides_the_key_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = throwaway_key(Path(tmp))
            creds = ka.load_credentials("sehr-geheime-kid", path)
            self.assertNotIn("sehr-geheime-kid", repr(creds))


class SigningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = throwaway_key(Path(self.tmp.name))
        self.creds = ka.load_credentials("kid", self.path)

    def test_a_signature_is_produced_and_is_base64(self):
        signature = ka.sign(self.creds, 1735689600000, "GET",
                            "/trade-api/v2/markets")
        self.assertTrue(base64.b64decode(signature))

    def test_the_signature_verifies_against_the_public_key(self):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        timestamp, method, path = 1735689600000, "GET", "/trade-api/v2/markets"
        signature = base64.b64decode(ka.sign(self.creds, timestamp, method, path))
        message = f"{timestamp}{method}{path}".encode()
        # Wirft, wenn die Signatur nicht passt.
        self.creds.private_key.public_key().verify(
            signature, message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256())

    def test_a_different_timestamp_changes_the_signed_message(self):
        first = ka.sign(self.creds, 1, "GET", "/trade-api/v2/markets")
        second = ka.sign(self.creds, 2, "GET", "/trade-api/v2/markets")
        self.assertNotEqual(first, second)

    def test_headers_carry_key_id_timestamp_and_signature(self):
        headers = ka.auth_headers(self.creds, "GET", "/trade-api/v2/markets",
                                  1735689600000)
        self.assertEqual(headers["KALSHI-ACCESS-KEY"], "kid")
        self.assertEqual(headers["KALSHI-ACCESS-TIMESTAMP"], "1735689600000")
        self.assertTrue(headers["KALSHI-ACCESS-SIGNATURE"])


class AvailabilityTests(unittest.TestCase):
    def test_absent_environment_means_not_available(self):
        import os

        saved = {k: os.environ.pop(k, None)
                 for k in (ka.KEY_ID_ENV, ka.PRIVATE_KEY_PATH_ENV)}
        try:
            self.assertFalse(ka.credentials_available())
        finally:
            for key, value in saved.items():
                if value is not None:
                    os.environ[key] = value

    def test_both_variables_present_means_available(self):
        import os

        saved = {k: os.environ.get(k) for k in (ka.KEY_ID_ENV,
                                                ka.PRIVATE_KEY_PATH_ENV)}
        os.environ[ka.KEY_ID_ENV] = "kid"
        os.environ[ka.PRIVATE_KEY_PATH_ENV] = "irgendwo.pem"
        try:
            self.assertTrue(ka.credentials_available())
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
