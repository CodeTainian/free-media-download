import ipaddress

import pytest

from app.security import (
    PLATFORM_DOMAINS,
    UnsafeUrlError,
    classify_url,
    is_public_ip,
    is_short_platform_url,
    resolve_public_host,
    safe_filename,
)


@pytest.mark.parametrize(
    ("url", "platform"),
    [
        ("https://www.youtube.com/watch?v=abc", "youtube"),
        ("https://vm.tiktok.com/abc", "tiktok"),
        ("https://x.com/user/status/1", "x"),
        ("https://vimeo.com/123", "vimeo"),
        ("https://www.douyin.com/video/123", "douyin"),
        ("https://www.xiaohongshu.com/explore/123", "xiaohongshu"),
        ("https://weibo.com/123/abc", "weibo"),
        ("https://v.qq.com/x/page/abc.html", "tencent-video"),
        ("https://www.mgtv.com/b/1/2.html", "mango-tv"),
        ("https://www.youku.com/v_show/id_abc.html", "youku"),
        ("https://www.dailymotion.com/video/abc", "dailymotion"),
        ("https://www.twitch.tv/videos/123", "twitch"),
        ("https://soundcloud.com/artist/track", "soundcloud"),
        ("https://www.bbc.co.uk/programmes/abc", "bbc"),
        ("https://archive.org/details/abc", "archive-org"),
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
        "https://v.qq.com.attacker.example/video",
        "https://douyin.com.attacker.example/video",
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


def test_catalog_covers_mainland_and_global_platforms():
    assert len(PLATFORM_DOMAINS) >= 60
    assert {"douyin", "bilibili", "weibo", "youku", "youtube", "tiktok", "vimeo"} <= set(
        PLATFORM_DOMAINS
    )


def test_normalizes_douyin_jingxuan_modal_link():
    platform, normalized = classify_url(
        "https://www.douyin.com/jingxuan?from=web&modal_id=7636370662940085510"
    )
    assert platform == "douyin"
    assert normalized == "https://www.douyin.com/video/7636370662940085510"


def test_does_not_rewrite_invalid_douyin_modal_id():
    _, normalized = classify_url("https://www.douyin.com/jingxuan?modal_id=../../etc/passwd")
    assert normalized == "https://www.douyin.com/jingxuan?modal_id=../../etc/passwd"


def test_does_not_override_direct_douyin_video_with_modal_query():
    _, normalized = classify_url("https://www.douyin.com/video/1234567890?modal_id=9876543210")
    assert normalized == "https://www.douyin.com/video/1234567890?modal_id=9876543210"


@pytest.mark.parametrize(
    "url",
    [
        "https://b23.tv/abc",
        "https://v.douyin.com/abc",
        "https://vm.tiktok.com/abc",
        "https://youtu.be/abc",
        "https://fb.watch/abc",
    ],
)
def test_identifies_known_platform_short_links(url):
    assert is_short_platform_url(url)


def test_sanitizes_filename():
    assert safe_filename('../../bad\x00:name?.mp4') == "bad name .mp4"


@pytest.mark.asyncio
async def test_resolver_blocks_loopback_before_request():
    with pytest.raises(UnsafeUrlError, match="Private and reserved"):
        await resolve_public_host("localhost", 80)
