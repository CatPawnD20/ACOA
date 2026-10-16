"""Server-side dashboard authentication and CSRF tokens; EP-07.02."""

import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field

PASSWORD_ITERATIONS = 600_000


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _valid_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@dataclass(frozen=True, slots=True)
class DashboardAuthenticator:
    """Verify one injected owner credential without retaining the plaintext password."""

    username: str = field(repr=False)
    password_salt: bytes = field(repr=False)
    password_pbkdf2_sha256: bytes = field(repr=False)
    iterations: int = field(default=PASSWORD_ITERATIONS, repr=False)

    def __post_init__(self) -> None:
        if not self.username or self.username != self.username.strip() or len(self.username) > 128:
            raise ValueError("Dashboard username must contain between 1 and 128 characters.")
        if not isinstance(self.password_salt, bytes) or len(self.password_salt) < 16:
            raise ValueError("Dashboard password salt must contain at least 16 bytes.")
        if (
            not isinstance(self.password_pbkdf2_sha256, bytes)
            or len(self.password_pbkdf2_sha256) != hashlib.sha256().digest_size
        ):
            raise ValueError("Dashboard password verifier must be PBKDF2-SHA256 output.")
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations < PASSWORD_ITERATIONS
        ):
            raise ValueError("Dashboard password verification requires sufficient work factor.")

    @classmethod
    def from_password(
        cls, username: str, password: str, *, salt: bytes | None = None
    ) -> "DashboardAuthenticator":
        """Build a memory-only verifier from caller-supplied startup credentials."""
        if not isinstance(password, str) or not 16 <= len(password) <= 1024:
            raise ValueError("Dashboard password must contain between 16 and 1024 characters.")
        selected_salt = salt if salt is not None else secrets.token_bytes(16)
        verifier = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), selected_salt, PASSWORD_ITERATIONS
        )
        return cls(username, selected_salt, verifier)

    def authenticate(self, username: str, password: str) -> str | None:
        if len(username) > 128 or len(password) > 1024:
            return None
        username_matches = hmac.compare_digest(username, self.username)
        supplied = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), self.password_salt, self.iterations
        )
        password_matches = hmac.compare_digest(supplied, self.password_pbkdf2_sha256)
        return _sha256(self.username) if username_matches and password_matches else None


@dataclass(frozen=True, slots=True)
class CsrfProtector:
    """Issue short-lived HMAC tokens bound to the authenticated dashboard owner."""

    key: bytes = field(repr=False)
    ttl_seconds: int = 3600
    clock: Callable[[], float] = field(default=time.time, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.key, bytes) or len(self.key) < 32:
            raise ValueError("CSRF signing key must contain at least 32 bytes.")
        if (
            isinstance(self.ttl_seconds, bool)
            or not isinstance(self.ttl_seconds, int)
            or not 60 <= self.ttl_seconds <= 86400
        ):
            raise ValueError("CSRF token lifetime must be between 60 seconds and one day.")

    def issue(self, actor_sha256: str) -> str:
        if not _valid_digest(actor_sha256):
            raise ValueError("CSRF tokens require an authenticated actor digest.")
        payload = f"{int(self.clock())}.{secrets.token_hex(16)}.{actor_sha256}"
        signature = hmac.new(self.key, payload.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{payload}.{signature}"

    def verify(self, token: str, actor_sha256: str) -> bool:
        if len(token) > 256 or not _valid_digest(actor_sha256):
            return False
        parts = token.split(".")
        if len(parts) != 4:
            return False
        issued_text, nonce, token_actor, supplied_signature = parts
        if len(nonce) != 32 or any(character not in "0123456789abcdef" for character in nonce):
            return False
        if not _valid_digest(supplied_signature) or not hmac.compare_digest(
            token_actor, actor_sha256
        ):
            return False
        payload = ".".join(parts[:3])
        expected = hmac.new(self.key, payload.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected):
            return False
        try:
            issued_at = int(issued_text)
        except ValueError:
            return False
        age = int(self.clock()) - issued_at
        return 0 <= age <= self.ttl_seconds


@dataclass(frozen=True, slots=True)
class DashboardSecurity:
    authenticator: DashboardAuthenticator = field(repr=False)
    csrf: CsrfProtector = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.authenticator, DashboardAuthenticator) or not isinstance(
            self.csrf, CsrfProtector
        ):
            raise ValueError("Dashboard security requires validated authentication and CSRF.")
