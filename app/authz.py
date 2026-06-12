"""Authorization logic for the terminal's admin gating.

Streamlit-free: the terminal wraps these helpers with ``st.secrets`` /
``st.user``; tests exercise the decision matrix directly.

Auth model (LAUNCH_PLAN §3): Streamlit-native ``st.login()`` with an OIDC
provider configured in ``.streamlit/secrets.toml [auth]``. Without that
section the app runs in open local-research mode — no login surface at all.
When auth is configured, the Settings page fails closed: it requires a
signed-in user whose e-mail is on the admin allowlist (``ADMIN_EMAILS`` env
or ``[admin].emails`` in secrets).
"""

from __future__ import annotations

from typing import Any

# Flat single-provider [auth] config needs all of these to let st.login() run.
_FLAT_PROVIDER_KEYS = ("client_id", "client_secret", "server_metadata_url")
_BASE_KEYS = ("redirect_uri", "cookie_secret")

# settings_access() reasons
ACCESS_OPEN = "open"
ACCESS_OK = "ok"
ACCESS_LOGIN_REQUIRED = "login_required"
ACCESS_NO_ALLOWLIST = "no_allowlist"
ACCESS_NOT_ALLOWED = "not_allowed"


def _filled(mapping: Any, key: str) -> bool:
    try:
        value = mapping[key]
    except Exception:
        return False
    return value is not None and str(value).strip() != ""


def auth_provider_from_secrets(auth_section: Any) -> str | None:
    """Classify the ``[auth]`` secrets section.

    Returns ``None`` when auth is off (section missing/incomplete), ``""``
    for a complete flat single-provider config (``st.login()`` without
    arguments), or the provider name for a ``[auth.<name>]`` sub-section
    config (``st.login(name)``).
    """

    if auth_section is None:
        return None
    try:
        keys = [str(key) for key in auth_section.keys()]
    except Exception:
        return None
    if not all(_filled(auth_section, key) for key in _BASE_KEYS):
        return None
    if all(_filled(auth_section, key) for key in _FLAT_PROVIDER_KEYS):
        return ""
    for key in keys:
        try:
            value = auth_section[key]
        except Exception:
            continue
        if not hasattr(value, "keys"):
            continue
        if _filled(value, "client_id") and _filled(value, "client_secret"):
            return key
    return None


def normalize_emails(value: Any) -> list[str]:
    """Coerce an allowlist value (list/tuple/set or comma string) to clean e-mails."""

    if value is None:
        return []
    items: list[Any]
    if isinstance(value, str):
        items = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]
    cleaned: list[str] = []
    for item in items:
        email = str(item or "").strip().lower()
        if email and "@" in email and email not in cleaned:
            cleaned.append(email)
    return cleaned


def admin_emails(env_value: Any, secrets_value: Any) -> list[str]:
    """Admin allowlist with env precedence: ``ADMIN_EMAILS`` wins over secrets."""

    from_env = normalize_emails(env_value)
    if from_env:
        return from_env
    return normalize_emails(secrets_value)


def settings_access(provider: str | None, user_email: Any, allowlist: list[str]) -> tuple[bool, str]:
    """Decide Settings/admin access. Fails closed whenever auth is configured.

    Returns ``(allowed, reason)`` — reasons: ``open`` (auth off, local mode),
    ``login_required``, ``no_allowlist`` (operator must configure admins),
    ``not_allowed``, ``ok``.
    """

    if provider is None:
        return True, ACCESS_OPEN
    email = str(user_email or "").strip().lower()
    if not email:
        return False, ACCESS_LOGIN_REQUIRED
    if not allowlist:
        return False, ACCESS_NO_ALLOWLIST
    if email not in allowlist:
        return False, ACCESS_NOT_ALLOWED
    return True, ACCESS_OK
