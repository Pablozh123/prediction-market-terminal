"""Kalshi request signing for market data, and nothing else.

Kalshi authenticates every request with an RSA-PSS signature over the
timestamp, the HTTP method and the path. The same signature scheme covers
market data and order placement, which is the problem this module exists to
solve: a credential that can read a book can also send an order, unless
something in the code path stops it.

So this module stops it. Only GET is signed, and any path that touches the
portfolio or order endpoints is refused before a signature is produced. Even a
key that was created with full trading rights cannot place an order through
here. That is a structural guarantee rather than a convention, because the
alternative - remembering not to call the wrong endpoint - is not a guarantee
at all.

Storage. The private key never lives in this repository. ``KALSHI_KEY_ID`` and
``KALSHI_PRIVATE_KEY_PATH`` come from the environment (``.env`` is gitignored,
including the ``.env.*`` family that Windows creates when it appends ``.txt``),
and the path itself is rejected if it points inside the repository. The repo is
public and gets attached to job applications; a gitignore rule protects against
accident, not against ``git add -f`` or someone zipping the folder.

Key material is never logged, never placed in an exception message, and never
returned by any function here.

Create the key with the READ scope. A key created without an explicit scope
gets both read and write.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

KEY_ID_ENV = "KALSHI_KEY_ID"
PRIVATE_KEY_PATH_ENV = "KALSHI_PRIVATE_KEY_PATH"

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Nur Lesezugriffe. Alles andere wird gar nicht erst signiert.
ALLOWED_METHODS = frozenset({"GET"})

#: Pfadfragmente, die zum Handel oder zum Konto gehoeren. Auch als GET nicht
#: noetig fuer Marktdaten, und der Blocklist-Eintrag kostet nichts.
BLOCKED_PATH_FRAGMENTS = ("/orders", "/portfolio", "/positions", "/fills",
                          "/settlements", "/transfers", "/withdrawals")


class CredentialError(RuntimeError):
    """Credentials are missing, unusable, or stored somewhere unsafe."""


class ForbiddenRequest(RuntimeError):
    """The request is outside what this module is allowed to sign."""


@dataclass(frozen=True)
class KalshiCredentials:
    """A key id plus a loaded private key. Never carries the PEM text."""

    key_id: str
    private_key: object
    source_path: Path

    def __repr__(self) -> str:  # pragma: no cover - triviale Absicherung
        return f"KalshiCredentials(key_id=<redacted>, source={self.source_path.name})"


def _is_inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return False
    return True


def check_request(method: str, path: str) -> None:
    """Refuse anything that is not a plain market-data read.

    Raises before any signing happens, so a blocked call cannot be sent even
    by accident.
    """
    verb = str(method or "").upper()
    if verb not in ALLOWED_METHODS:
        raise ForbiddenRequest(
            f"{verb or '<leer>'} wird hier nicht signiert. Dieses Modul "
            f"signiert ausschliesslich {'/'.join(sorted(ALLOWED_METHODS))} "
            f"fuer Marktdaten."
        )
    lowered = str(path or "").lower()
    for fragment in BLOCKED_PATH_FRAGMENTS:
        if fragment in lowered:
            raise ForbiddenRequest(
                f"Pfad {path} enthaelt '{fragment}' und gehoert zu Konto oder "
                f"Order-Pfad. Dieses Modul signiert nur Marktdaten."
            )


def load_credentials(key_id: str | None = None,
                     private_key_path: str | os.PathLike | None = None,
                     allow_in_repo: bool = False) -> KalshiCredentials:
    """Read the key id and private key from the environment, with guards.

    ``allow_in_repo`` exists only so the tests can use a temporary key inside a
    scratch directory; real credentials must live outside the repository.
    """
    key_id = (key_id if key_id is not None
              else os.environ.get(KEY_ID_ENV, "")).strip()
    raw_path = (str(private_key_path) if private_key_path is not None
                else os.environ.get(PRIVATE_KEY_PATH_ENV, "")).strip()

    if not key_id:
        raise CredentialError(
            f"{KEY_ID_ENV} ist nicht gesetzt. Key-Id und Pfad gehoeren in .env, "
            f"der Schluessel selbst nicht."
        )
    if not raw_path:
        raise CredentialError(
            f"{PRIVATE_KEY_PATH_ENV} ist nicht gesetzt. Er zeigt auf die "
            f"PEM-Datei ausserhalb des Repos."
        )

    path = Path(raw_path).expanduser()
    if not path.exists():
        raise CredentialError(f"Private-Key-Datei nicht gefunden: {path}")
    if not allow_in_repo and _is_inside_repo(path):
        raise CredentialError(
            f"Die Private-Key-Datei liegt im Repository ({path}). Das Repo ist "
            f"oeffentlich; eine gitignore-Regel schuetzt nur gegen Versehen. "
            f"Verschiebe die Datei nach ausserhalb, etwa nach "
            f"%USERPROFILE%\\.kalshi\\, und passe {PRIVATE_KEY_PATH_ENV} an."
        )

    try:
        from cryptography.hazmat.primitives import serialization
    except ImportError as exc:  # pragma: no cover - Abhaengigkeit fehlt
        raise CredentialError(
            "Das Paket cryptography wird zum Signieren gebraucht."
        ) from exc

    try:
        data = path.read_bytes()
        private_key = serialization.load_pem_private_key(data, password=None)
    except Exception as exc:  # noqa: BLE001
        # Bewusst ohne Details: die Ausnahme koennte Schluesselmaterial tragen.
        raise CredentialError(
            f"Private-Key-Datei {path.name} liess sich nicht als PEM lesen "
            f"({type(exc).__name__}). Erwartet wird die unverschluesselte "
            f"PEM-Datei aus der Kalshi-Oberflaeche."
        ) from None

    return KalshiCredentials(key_id=key_id, private_key=private_key,
                             source_path=path)


def sign(credentials: KalshiCredentials, timestamp_ms: int, method: str,
         path: str) -> str:
    """RSA-PSS SHA-256 signature over ``timestamp + METHOD + path``, base64."""
    check_request(method, path)
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    message = f"{int(timestamp_ms)}{str(method).upper()}{path}".encode()
    signature = credentials.private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode()


def auth_headers(credentials: KalshiCredentials, method: str, path: str,
                 timestamp_ms: int) -> dict[str, str]:
    """The three headers Kalshi expects on a signed request."""
    return {
        "KALSHI-ACCESS-KEY": credentials.key_id,
        "KALSHI-ACCESS-TIMESTAMP": str(int(timestamp_ms)),
        "KALSHI-ACCESS-SIGNATURE": sign(credentials, timestamp_ms, method, path),
    }


def credentials_available() -> bool:
    """Are both environment variables set? Says nothing about validity."""
    return bool(os.environ.get(KEY_ID_ENV, "").strip()
                and os.environ.get(PRIVATE_KEY_PATH_ENV, "").strip())


#: Wo nach den beiden Variablen gesucht wird, in dieser Reihenfolge. Der
#: Zusatzpfad erlaubt eine gemeinsame Secret-Datei ausserhalb dieses Repos.
ENV_FILE_OVERRIDE = "KALSHI_ENV_FILE"


def read_selected_env(path: str | os.PathLike,
                      keys: tuple[str, ...] = (KEY_ID_ENV, PRIVATE_KEY_PATH_ENV)
                      ) -> dict[str, str]:
    """Read ONLY the named keys out of a dotenv-style file.

    Deliberately selective. A shared secrets file usually holds far more than
    this process should ever see - wallet private keys, exchange secrets, model
    API keys. Sourcing the whole file would pull all of that into a read-only
    research recorder for no reason. Anything not named here is not even parsed
    into memory.
    """
    wanted = set(keys)
    found: dict[str, str] = {}
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        name = name.strip()
        if name not in wanted:
            continue
        found[name] = value.strip().strip('"').strip("'")
    return found


def env_file_candidates() -> list[Path]:
    """Files that may carry the two Kalshi variables, most specific first.

    ``KALSHI_ENV_FILE`` may itself be written in the project's own ``.env``
    rather than exported, which is the normal case for a scheduled task: it
    inherits the logon environment and knows nothing about this project. So the
    project file is consulted for the pointer as well as for the values.
    """
    candidates: list[Path] = []
    override = os.environ.get(ENV_FILE_OVERRIDE, "").strip()
    project_env = REPO_ROOT / ".env"
    if not override:
        pointed = read_selected_env(project_env, (ENV_FILE_OVERRIDE,))
        override = pointed.get(ENV_FILE_OVERRIDE, "").strip()
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(project_env)
    return candidates


def load_from_env_files(paths: list[Path] | None = None) -> dict[str, str]:
    """Fill the two variables from the first file that supplies them.

    Values already present in the environment win, so an explicitly exported
    variable is never silently overridden by a file.
    """
    loaded: dict[str, str] = {}
    for path in (paths if paths is not None else env_file_candidates()):
        for name, value in read_selected_env(path).items():
            if value and not os.environ.get(name, "").strip():
                os.environ[name] = value
                loaded[name] = str(path)
    return loaded
