"""Fernet-based encryption for API keys and other sensitive values stored at rest.

Key lifecycle
─────────────
  • On first boot: generate a new Fernet key and write it to ~/.vloop/.key
    with permissions 0600 (owner read/write only).
  • On subsequent boots: load the key from that file.
  • All provider API keys are stored as Fernet-encrypted ciphertext (base64 token).

Graceful degradation
────────────────────
  If the ``cryptography`` package is not installed the vault operates in
  *pass-through* mode — values are stored/returned as-is (no encryption).
  A warning is emitted once so operators know their data is unprotected.
"""

from __future__ import annotations

import os
import stat
import warnings
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken

    _HAS_CRYPTO = True
except ImportError:  # pragma: no cover
    _HAS_CRYPTO = False


class SecretVault:
    """Manages a symmetric Fernet key and encrypts/decrypts secret strings."""

    def __init__(self, key_path: Path) -> None:
        self.key_path = key_path
        self._fernet: "Fernet | None" = None
        self._init_key()

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    def _init_key(self) -> None:
        if not _HAS_CRYPTO:
            warnings.warn(
                "The 'cryptography' package is not installed. "
                "API keys will be stored WITHOUT encryption. "
                "Install it with: pip install cryptography",
                RuntimeWarning,
                stacklevel=2,
            )
            return

        if self.key_path.exists():
            key = self.key_path.read_bytes()
        else:
            key = Fernet.generate_key()
            self.key_path.write_bytes(key)
            # Owner read/write only — keep the key secret
            os.chmod(self.key_path, stat.S_IRUSR | stat.S_IWUSR)

        self._fernet = Fernet(key)

    # ── Public API ────────────────────────────────────────────────────────────

    def encrypt(self, plaintext: str) -> str:
        """Return a Fernet token (base64 string) for *plaintext*.

        Falls back to returning plaintext unchanged if ``cryptography`` is absent.
        """
        if not self._fernet:
            return plaintext
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a Fernet token and return the original plaintext.

        Returns an empty string on any decryption error rather than raising.
        Falls back to returning *ciphertext* unchanged if ``cryptography`` is absent.
        """
        if not self._fernet:
            return ciphertext
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except Exception:
            return ""

    @property
    def is_available(self) -> bool:
        """True when real Fernet encryption is active."""
        return _HAS_CRYPTO and self._fernet is not None
