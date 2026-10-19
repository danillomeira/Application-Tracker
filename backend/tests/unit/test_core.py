from __future__ import annotations

import pytest

from tracker.core.crypto import DecryptionError, decrypt, decrypt_json, encrypt, encrypt_json
from tracker.core.logging import redact
from tracker.core.security import read_session, sign_session
from tracker.core.settings_store import SettingError, validate
from tracker.core.storage import LocalStorage
from tracker.integrations.claude.pricing import cost_usd


def test_encrypt_roundtrip() -> None:
    blob = encrypt(b"segredo")
    assert blob != b"segredo"
    assert decrypt(blob) == b"segredo"
    assert decrypt_json(encrypt_json({"a": 1})) == {"a": 1}


def test_decrypt_tampered_fails() -> None:
    blob = bytearray(encrypt(b"segredo"))
    blob[-1] ^= 1
    with pytest.raises(DecryptionError):
        decrypt(bytes(blob))


def test_decrypt_wrong_key_fails() -> None:
    blob = encrypt(b"x")
    with pytest.raises(DecryptionError):
        decrypt(blob, key=b"k" * 32)


def test_session_only_for_allowed_email() -> None:
    assert read_session(sign_session("me@example.com")) == "me@example.com"
    assert read_session(sign_session("other@example.com")) is None
    assert read_session("garbage") is None
    assert read_session(None) is None


def test_redact_secrets() -> None:
    out = redact("key sk-ant-api03-abcdefghijklmnop and Bearer ya29.xyz refresh_token=abc123")
    assert "abcdefghijklmnop" not in out
    assert "ya29.xyz" not in out
    assert "abc123" not in out


def test_email_and_linkedin_send_policy_is_immutable() -> None:
    with pytest.raises(SettingError):
        validate("automation_policy", {"email": {"send": "auto"}})
    with pytest.raises(SettingError):
        validate("automation_policy", {"linkedin_messages": {"send": "auto"}})
    validate("automation_policy", {"easy_apply": {"mode": "auto"}})
    with pytest.raises(SettingError):
        validate("unknown_key", {})


def test_local_storage_blocks_traversal(tmp_path) -> None:
    st = LocalStorage(tmp_path)
    key = st.put("../../etc/passwd", b"x")
    assert key == "etc/passwd"
    assert (tmp_path / "etc" / "passwd").exists()
    assert st.list("etc") == ["etc/passwd"]


def test_cost_calculation() -> None:
    c = cost_usd("claude-opus-5-5", input_tokens=1_000_000, output_tokens=100_000)
    assert c == pytest.approx(4.0 + 2.0)
    c2 = cost_usd("claude-opus-5-5", input_tokens=0, output_tokens=0, web_search_requests=3)
    assert c2 == pytest.approx(0.03)
