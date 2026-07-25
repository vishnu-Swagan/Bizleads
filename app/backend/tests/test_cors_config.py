from main import _DEFAULT_ORIGINS, _parse_allowed_origins


def test_unset_falls_back_to_localhost_defaults():
    # os.environ.get("ALLOWED_ORIGINS") returns None when the var isn't set at
    # all - distinct from an explicitly empty string, which must NOT fall back
    # (see test_empty_string_fails_closed below).
    assert _parse_allowed_origins(None) == _DEFAULT_ORIGINS.split(",")


def test_normal_comma_separated_list_is_parsed():
    assert _parse_allowed_origins("https://a.example.com,https://b.example.com") == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_whitespace_and_trailing_comma_are_cleaned():
    assert _parse_allowed_origins(" https://a.example.com , https://b.example.com ,") == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_empty_string_fails_closed():
    # An explicit ALLOWED_ORIGINS="" must NOT fall back to the localhost
    # defaults - it must produce an empty allowlist, so CORS fails closed
    # rather than silently reopening. Pinning this deliberately since it's
    # easy to get backwards with a truthy/falsy check on the raw value.
    assert _parse_allowed_origins("") == []


def test_bare_wildcard_is_dropped():
    # A bare "*" must never reach CORSMiddleware's allow_origins: combined
    # with allow_credentials=True, Starlette treats "*" as allow_all_origins
    # and echoes back any Origin header with credentials allowed - the exact
    # vulnerability this allowlist replaces.
    assert _parse_allowed_origins("*") == []


def test_wildcard_mixed_with_real_origin_is_dropped_but_real_origin_kept():
    result = _parse_allowed_origins("https://good.com,*")
    assert "*" not in result
    assert result == ["https://good.com"]
