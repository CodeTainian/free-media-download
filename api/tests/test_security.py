import ipaddress

import pytest

from app.security import UnsafeUrlError, classify_url, is_public_ip, resolve_public_host, safe_filename


@pytest.mark.parametrize(
    ("url", "platform"),
    [
        ("https://www.youtube.com/watch?v=abc", "youtube"),
        ("https://vm.tiktok.com/abc", "tiktok"),
        ("https://x.com/user/status/1", "x"),
        ("https://vimeo.com/123", "vimeo"),
        ("https://media.example.org/video.mp4", "direct"),
    ],
)
def test_classifies_allowed_urls(url, platform):
    assert classify_url(url)[0] == platform


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://youtube.com.attacker.example/video",
        "https://user:pass@youtube.com/video",
        "https://youtube.com:8443/video",
        "http://127.0.0.1/private.mp4",
        "http://[::1]/private.mp4",
        "https://example.org/page",
    ],
)
def test_rejects_unsafe_or_unsupported_urls(url):
    with pytest.raises(UnsafeUrlError):
        classify_url(url)


@pytest.mark.parametrize("value", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "192.168.1.1"])
def test_rejects_non_public_ips(value):
    assert not is_public_ip(value)


def test_accepts_public_ip():
    assert is_public_ip("1.1.1.1")


def test_sanitizes_filename():
    assert safe_filename('../../bad\x00:name?.mp4') == "bad name .mp4"


@pytest.mark.asyncio
async def test_resolver_blocks_loopback_before_request():
    with pytest.raises(UnsafeUrlError, match="Private and reserved"):
        await resolve_public_host("localhost", 80)
