import unittest

from app import authz


class AuthProviderTests(unittest.TestCase):
    FLAT = {
        "redirect_uri": "http://localhost:8503/oauth2callback",
        "cookie_secret": "secret",
        "client_id": "id",
        "client_secret": "cs",
        "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
    }

    def test_missing_section_means_auth_off(self) -> None:
        self.assertIsNone(authz.auth_provider_from_secrets(None))

    def test_empty_section_means_auth_off(self) -> None:
        self.assertIsNone(authz.auth_provider_from_secrets({}))

    def test_incomplete_flat_config_means_auth_off(self) -> None:
        for missing in ("redirect_uri", "cookie_secret", "client_id"):
            section = dict(self.FLAT)
            section[missing] = ""
            self.assertIsNone(authz.auth_provider_from_secrets(section), missing)

    def test_complete_flat_config_is_default_provider(self) -> None:
        self.assertEqual(authz.auth_provider_from_secrets(self.FLAT), "")

    def test_named_provider_subsection(self) -> None:
        section = {
            "redirect_uri": "http://localhost:8503/oauth2callback",
            "cookie_secret": "secret",
            "google": {"client_id": "id", "client_secret": "cs"},
        }
        self.assertEqual(authz.auth_provider_from_secrets(section), "google")

    def test_subsection_without_credentials_means_auth_off(self) -> None:
        section = {
            "redirect_uri": "http://localhost:8503/oauth2callback",
            "cookie_secret": "secret",
            "google": {"client_id": ""},
        }
        self.assertIsNone(authz.auth_provider_from_secrets(section))

    def test_non_mapping_section_means_auth_off(self) -> None:
        self.assertIsNone(authz.auth_provider_from_secrets("nope"))


class NormalizeEmailsTests(unittest.TestCase):
    def test_comma_string_lowercased_and_deduped(self) -> None:
        self.assertEqual(
            authz.normalize_emails("You@Example.com, second@x.io; YOU@example.com ,,"),
            ["you@example.com", "second@x.io"],
        )

    def test_list_input(self) -> None:
        self.assertEqual(authz.normalize_emails(["A@b.c", None, "  "]), ["a@b.c"])

    def test_entries_without_at_sign_are_dropped(self) -> None:
        self.assertEqual(authz.normalize_emails("admin, a@b.c"), ["a@b.c"])

    def test_none_is_empty(self) -> None:
        self.assertEqual(authz.normalize_emails(None), [])


class AdminEmailsTests(unittest.TestCase):
    def test_env_wins_over_secrets(self) -> None:
        self.assertEqual(authz.admin_emails("env@x.io", ["secret@x.io"]), ["env@x.io"])

    def test_falls_back_to_secrets(self) -> None:
        self.assertEqual(authz.admin_emails("", ["secret@x.io"]), ["secret@x.io"])

    def test_both_empty(self) -> None:
        self.assertEqual(authz.admin_emails("", None), [])


class SettingsAccessTests(unittest.TestCase):
    def test_auth_off_is_open_local_mode(self) -> None:
        self.assertEqual(authz.settings_access(None, "", []), (True, authz.ACCESS_OPEN))

    def test_anonymous_user_must_log_in(self) -> None:
        self.assertEqual(
            authz.settings_access("", "", ["a@b.c"]),
            (False, authz.ACCESS_LOGIN_REQUIRED),
        )

    def test_logged_in_without_allowlist_fails_closed(self) -> None:
        self.assertEqual(
            authz.settings_access("", "a@b.c", []),
            (False, authz.ACCESS_NO_ALLOWLIST),
        )

    def test_logged_in_not_on_allowlist(self) -> None:
        self.assertEqual(
            authz.settings_access("google", "other@b.c", ["a@b.c"]),
            (False, authz.ACCESS_NOT_ALLOWED),
        )

    def test_allowlisted_email_case_insensitive(self) -> None:
        self.assertEqual(
            authz.settings_access("", "  A@B.C ", ["a@b.c"]),
            (True, authz.ACCESS_OK),
        )


if __name__ == "__main__":
    unittest.main()
