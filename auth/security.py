"""Security utilities for authentication.

The module uses PBKDF2-HMAC-SHA256 with a per-password random salt. This keeps
local SQLite authentication independent from external packages and avoids plain
text password storage.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from config import settings


@dataclass(frozen=True)
class PasswordHash:
    """Structured representation of a stored password hash."""

    salt: str
    digest: str
    iterations: int

    def serialize(self) -> str:
        """Serialize the hash for database storage."""

        return f"pbkdf2_sha256${self.iterations}${self.salt}${self.digest}"


class PasswordHasher:
    """Hash and verify passwords with constant-time comparison."""

    algorithm = "sha256"

    @staticmethod
    def hash_password(password: str) -> str:
        """Return a salted hash for a plain password."""

        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            PasswordHasher.algorithm,
            password.encode("utf-8"),
            salt.encode("utf-8"),
            settings.password_iterations,
        ).hex()
        return PasswordHash(salt, digest, settings.password_iterations).serialize()

    @staticmethod
    def verify_password(password: str, stored_hash: str) -> bool:
        """Verify a password against its serialized database hash."""

        try:
            method, iterations, salt, digest = stored_hash.split("$", 3)
            if method != "pbkdf2_sha256":
                return False
            candidate = hashlib.pbkdf2_hmac(
                PasswordHasher.algorithm,
                password.encode("utf-8"),
                salt.encode("utf-8"),
                int(iterations),
            ).hex()
            return hmac.compare_digest(candidate, digest)
        except (ValueError, TypeError):
            return False
