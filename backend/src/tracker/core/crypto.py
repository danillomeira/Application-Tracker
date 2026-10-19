"""Criptografia simétrica (AES-256-GCM) para tokens, cookies e backups.

Formato: versão (1 byte) | nonce (12 bytes) | ciphertext+tag.
"""

from __future__ import annotations

import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from tracker.core.config import get_settings

_VERSION = b"\x01"


class DecryptionError(Exception):
    pass


def encrypt(plaintext: bytes, key: bytes | None = None) -> bytes:
    k = key or get_settings().encryption_key_bytes
    nonce = os.urandom(12)
    return _VERSION + nonce + AESGCM(k).encrypt(nonce, plaintext, _VERSION)


def decrypt(blob: bytes, key: bytes | None = None) -> bytes:
    k = key or get_settings().encryption_key_bytes
    if len(blob) < 29 or blob[:1] != _VERSION:
        raise DecryptionError("formato inválido")
    try:
        return AESGCM(k).decrypt(blob[1:13], blob[13:], _VERSION)
    except Exception as exc:
        raise DecryptionError("falha ao descriptografar") from exc


def encrypt_json(data: Any) -> bytes:
    return encrypt(json.dumps(data).encode())


def decrypt_json(blob: bytes) -> Any:
    return json.loads(decrypt(blob))
