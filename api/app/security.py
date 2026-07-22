from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


PLATFORM_DOMAINS: dict[str, tuple[str, ...]] = {
    "youtube": ("youtube.com", "youtu.be", "youtube-nocookie.com"),
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com",),
    "x": ("x.com", "twitter.com"),
    "facebook": ("facebook.com", "fb.watch"),
    "reddit": ("reddit.com", "redd.it"),
    "vimeo": ("vimeo.com",),
    "bilibili": ("bilibili.com", "b23.tv"),
}

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
            return platform, normalized

    suffix = Path(urlsplit(normalized).path).suffix.lower()
    if suffix in DIRECT_EXTENSIONS:
        return "direct", normalized

    raise UnsafeUrlError(
        "SaveBolt currently supports YouTube, TikTok, Instagram, X, Facebook, Reddit, Vimeo, Bilibili, and public media file links."
    )


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
