from app.core.security import (
    LoginRateLimiter,
    create_session_token,
    decode_session_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    h = hash_password("s3cret!")
    assert h != "s3cret!"
    assert h.startswith("$argon2id$")
    assert verify_password("s3cret!", h)
    assert not verify_password("wrong", h)


def test_session_token_roundtrip() -> None:
    token = create_session_token(user_id=42, role="admin")
    payload = decode_session_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"


def test_session_token_tampered_is_rejected() -> None:
    token = create_session_token(user_id=1, role="user")
    assert decode_session_token(token + "x") is None


def test_login_rate_limiter() -> None:
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60)
    assert limiter.allow("1.2.3.4")
    assert limiter.allow("1.2.3.4")
    assert limiter.allow("1.2.3.4")
    assert not limiter.allow("1.2.3.4")
    assert limiter.allow("5.6.7.8")  # other clients are unaffected
