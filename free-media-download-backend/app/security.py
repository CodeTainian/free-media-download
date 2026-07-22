from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit


PLATFORM_DOMAINS: dict[str, tuple[str, ...]] = {
    # Mainland China
    "bilibili": ("bilibili.com", "b23.tv"),
    "douyin": ("douyin.com", "iesdouyin.com"),
    "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
    "weibo": ("weibo.com", "weibo.cn"),
    "ixigua": ("ixigua.com",),
    "toutiao": ("toutiao.com",),
    "acfun": ("acfun.cn",),
    "youku": ("youku.com", "tudou.com"),
    "iqiyi": ("iqiyi.com", "iq.com"),
    "tencent-video": ("v.qq.com", "film.qq.com"),
    "mango-tv": ("mgtv.com",),
    "douyu": ("douyu.com",),
    "huya": ("huya.com",),
    "cctv": ("cctv.com", "cntv.cn"),
    "sohu-video": ("tv.sohu.com", "my.tv.sohu.com"),
    "sina-video": ("video.sina.com.cn",),
    "ximalaya": ("ximalaya.com",),
    "netease-music": ("music.163.com",),
    "qq-music": ("y.qq.com",),
    "zhihu": ("zhihu.com",),
    # Global platforms and public broadcasters
    "youtube": ("youtube.com", "youtu.be", "youtube-nocookie.com"),
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com",),
    "x": ("x.com", "twitter.com"),
    "facebook": ("facebook.com", "fb.watch"),
    "reddit": ("reddit.com", "redd.it"),
    "vimeo": ("vimeo.com",),
    "dailymotion": ("dailymotion.com", "dai.ly"),
    "twitch": ("twitch.tv",),
    "soundcloud": ("soundcloud.com",),
    "bandcamp": ("bandcamp.com",),
    "mixcloud": ("mixcloud.com",),
    "pinterest": ("pinterest.com", "pin.it"),
    "tumblr": ("tumblr.com",),
    "linkedin": ("linkedin.com",),
    "snapchat": ("snapchat.com",),
    "streamable": ("streamable.com",),
    "rumble": ("rumble.com",),
    "odysee": ("odysee.com", "lbry.tv"),
    "vk": ("vk.com",),
    "rutube": ("rutube.ru",),
    "ok": ("ok.ru",),
    "mailru": ("my.mail.ru",),
    "niconico": ("nicovideo.jp", "niconico.jp"),
    "naver": ("tv.naver.com", "chzzk.naver.com"),
    "kakao-tv": ("tv.kakao.com",),
    "ted": ("ted.com",),
    "bbc": ("bbc.com", "bbc.co.uk"),
    "cnn": ("cnn.com",),
    "nbc": ("nbc.com", "nbcnews.com", "msnbc.com"),
    "cbs": ("cbs.com",),
    "fox": ("fox.com", "foxnews.com"),
    "espn": ("espn.com",),
    "arte": ("arte.tv",),
    "crunchyroll": ("crunchyroll.com",),
    "apple-podcasts": ("podcasts.apple.com",),
    "archive-org": ("archive.org",),
    "imgur": ("imgur.com",),
    "flickr": ("flickr.com",),
    "kickstarter": ("kickstarter.com",),
    "bluesky": ("bsky.app",),
    "dropbox": ("dropbox.com",),
    "google-drive": ("drive.google.com",),
    "vidio": ("vidio.com",),
    "viu": ("viu.com",),
    "peertube": ("framatube.org", "peertube.debian.social"),
}

SHORT_LINK_DOMAINS = frozenset(
    {
        "b23.tv",
        "dai.ly",
        "fb.watch",
        "pin.it",
        "redd.it",
        "v.douyin.com",
        "vm.tiktok.com",
        "xhslink.com",
        "youtu.be",
    }
)

DIRECT_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".mov",
    ".webm",
    ".mkv",
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
    ".ogg",
    ".opus",
}


class UnsafeUrlError(ValueError):
    pass


def _domain_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def _normalize_platform_url(platform: str, normalized: str) -> str:
    if platform != "douyin":
        return normalized
    parsed = urlsplit(normalized)
    if parsed.path.rstrip("/") not in {"", "/discover", "/jingxuan"}:
        return normalized
    modal_ids = parse_qs(parsed.query).get("modal_id", [])
    if len(modal_ids) == 1 and re.fullmatch(r"[0-9]{10,30}", modal_ids[0]):
        return f"https://www.douyin.com/video/{modal_ids[0]}"
    return normalized


def parse_public_http_url(raw_url: str) -> tuple[str, str, int]:
    try:
        parsed = urlsplit(raw_url.strip())
        port = parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("This link is not a valid URL.") from exc

    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("Only public http and https links are supported.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeUrlError("This link has an invalid host.")
    if port and port not in {80, 443}:
        raise UnsafeUrlError("Custom network ports are not supported.")

    host = parsed.hostname.rstrip(".").lower()
    try:
        literal_address = ipaddress.ip_address(host)
    except ValueError:
        literal_address = None
    if literal_address is not None and not is_public_ip(host):
        raise UnsafeUrlError("Private and reserved network addresses are blocked.")
    normalized = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))
    return normalized, host, port or (443 if parsed.scheme == "https" else 80)


def classify_url(raw_url: str) -> tuple[str, str]:
    normalized, host, _ = parse_public_http_url(raw_url)
    for platform, domains in PLATFORM_DOMAINS.items():
        if any(_domain_matches(host, domain) for domain in domains):
            return platform, _normalize_platform_url(platform, normalized)

    suffix = Path(urlsplit(normalized).path).suffix.lower()
    if suffix in DIRECT_EXTENSIONS:
        return "direct", normalized

    raise UnsafeUrlError(
        "SaveBolt supports recognized public media links from its platform catalog and direct media file links."
    )


def is_short_platform_url(raw_url: str) -> bool:
    try:
        _, host, _ = parse_public_http_url(raw_url)
    except UnsafeUrlError:
        return False
    return host in SHORT_LINK_DOMAINS


def is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(address.is_global and not address.is_multicast and not address.is_unspecified)


async def resolve_public_host(host: str, port: int) -> list[dict[str, object]]:
    loop = asyncio.get_running_loop()
    try:
        records = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError("The media host could not be resolved.") from exc

    resolved: list[dict[str, object]] = []
    seen: set[str] = set()
    for family, _, proto, _, sockaddr in records:
        ip = sockaddr[0]
        if ip in seen:
            continue
        if not is_public_ip(ip):
            raise UnsafeUrlError("Private and reserved network addresses are blocked.")
        seen.add(ip)
        resolved.append(
            {
                "hostname": host,
                "host": ip,
                "port": port,
                "family": family,
                "proto": proto,
                "flags": socket.AI_NUMERICHOST,
            }
        )
    if not resolved:
        raise UnsafeUrlError("The media host did not resolve to a public address.")
    return resolved


def safe_filename(value: str, fallback: str = "savebolt-download") -> str:
    cleaned = re.sub(r"[\x00-\x1f\x7f/\\:*?\"<>|]+", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned or fallback)[:180]


def redacted_url(raw_url: str) -> str:
    try:
        parsed = urlsplit(raw_url)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except ValueError:
        return "invalid-url"
