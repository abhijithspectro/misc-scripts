from dhi_catalog_check.docker_lookup import build_ref, sanitize_error


def test_build_ref() -> None:
    assert build_ref("cilium", "1.19.6") == "dhi.io/cilium:1.19.6"
    assert build_ref("busybox", "1.37", registry="dhi.io") == "dhi.io/busybox:1.37"


def test_sanitize_error_redacts_tokens() -> None:
    raw = "Authorization: Bearer super-secret-token-value denied"
    cleaned = sanitize_error(raw)
    assert "super-secret-token-value" not in cleaned
    assert "<redacted>" in cleaned
