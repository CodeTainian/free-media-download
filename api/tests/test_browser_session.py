import stat
from unittest.mock import AsyncMock, Mock

import pytest

from app.browser_session import (
    AnonymousBrowserSessionManager,
    BrowserSession,
    BrowserSessionError,
)
from app.config import Settings
from app.downloader import YtDlpService


@pytest.mark.asyncio
async def test_resolved_platform_args_use_managed_douyin_session(tmp_path):
    cookies = tmp_path / "douyin.cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    manager = AsyncMock()
    manager.ensure.return_value = BrowserSession(cookies, "Managed UA", 999999)
    service = YtDlpService(Settings(data_dir=tmp_path), browser_sessions=manager)

    args = await service._resolved_platform_args(
        "douyin", "https://www.douyin.com/video/7636370662940085510"
    )

    assert args == [
        "--impersonate",
        "chrome",
        "--user-agent",
        "Managed UA",
        "--cookies",
        str(cookies),
    ]
    manager.ensure.assert_awaited_once_with(
        "douyin", "https://www.douyin.com/video/7636370662940085510", force=False
    )


@pytest.mark.asyncio
async def test_explicit_douyin_cookie_source_takes_priority(tmp_path):
    manager = AsyncMock()
    service = YtDlpService(
        Settings(
            data_dir=tmp_path,
            cookies_from_browser="firefox",
            cookie_platforms=frozenset({"douyin"}),
        ),
        browser_sessions=manager,
    )

    args = await service._resolved_platform_args(
        "douyin", "https://www.douyin.com/video/7636370662940085510"
    )

    assert args == ["--cookies-from-browser", "firefox"]
    manager.ensure.assert_not_awaited()


@pytest.mark.asyncio
async def test_managed_douyin_impersonation_can_be_disabled(tmp_path):
    cookies = tmp_path / "douyin.cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    manager = AsyncMock()
    manager.ensure.return_value = BrowserSession(cookies, "Managed UA", 999999)
    service = YtDlpService(
        Settings(data_dir=tmp_path, browser_impersonate=None), browser_sessions=manager
    )

    args = await service._resolved_platform_args(
        "douyin", "https://www.douyin.com/video/7636370662940085510"
    )

    assert args == ["--user-agent", "Managed UA", "--cookies", str(cookies)]


def test_anonymous_browser_rejects_non_video_url_before_launch(tmp_path):
    manager = AnonymousBrowserSessionManager(Settings(data_dir=tmp_path))
    with pytest.raises(BrowserSessionError, match="invalid Douyin"):
        manager._bootstrap_douyin("https://www.douyin.com/jingxuan?modal_id=123")


def test_managed_cookie_file_is_private_netscape_format(tmp_path):
    manager = AnonymousBrowserSessionManager(Settings(data_dir=tmp_path))
    manager._write_cookie_file(
        [
            {
                "domain": ".douyin.com",
                "path": "/",
                "secure": True,
                "expires": 1234567890,
                "name": "s_v_web_id",
                "value": "anonymous-value",
            }
        ]
    )

    content = manager._cookies_file.read_text()
    assert content.startswith("# Netscape HTTP Cookie File\n")
    assert ".douyin.com\tTRUE\t/\tTRUE\t1234567890\ts_v_web_id\tanonymous-value" in content
    assert stat.S_IMODE(manager._cookies_file.stat().st_mode) == 0o600


def test_waits_until_douyin_issues_required_cookie(tmp_path, monkeypatch):
    manager = AnonymousBrowserSessionManager(
        Settings(data_dir=tmp_path, browser_cookie_wait_seconds=5)
    )
    read_cookies = Mock(
        side_effect=[
            [],
            [
                {
                    "domain": ".douyin.com",
                    "name": "s_v_web_id",
                    "value": "anonymous-value",
                },
                {"domain": ".douyin.com", "name": "ttwid", "value": "anonymous-value"},
                {"domain": ".douyin.com", "name": "__ac_nonce", "value": "anonymous-value"},
                {
                    "domain": ".douyin.com",
                    "name": "__ac_signature",
                    "value": "anonymous-value",
                },
                {"domain": ".douyin.com", "name": "odin_tt", "value": "anonymous-value"},
                {"domain": ".douyin.com", "name": "UIFID", "value": "anonymous-value"},
            ],
        ]
    )
    monkeypatch.setattr(manager, "_read_cookies", read_cookies)
    monkeypatch.setattr("app.browser_session.time.sleep", lambda _: None)

    cookies = manager._wait_for_douyin_cookies({"webSocketDebuggerUrl": "ws://test"})

    assert cookies[0]["name"] == "s_v_web_id"
    assert read_cookies.call_count == 2


@pytest.mark.asyncio
async def test_close_removes_managed_cookie_file(tmp_path):
    manager = AnonymousBrowserSessionManager(Settings(data_dir=tmp_path))
    manager._write_cookie_file(
        [
            {
                "domain": ".douyin.com",
                "path": "/",
                "name": "s_v_web_id",
                "value": "anonymous-value",
            }
        ]
    )

    await manager.close()

    assert not manager._cookies_file.exists()


@pytest.mark.asyncio
async def test_managed_session_is_reused_until_forced(tmp_path, monkeypatch):
    manager = AnonymousBrowserSessionManager(Settings(data_dir=tmp_path))
    cookies = tmp_path / "cached.cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    bootstrap = Mock(return_value=BrowserSession(cookies, "Managed UA", 999999999))
    monkeypatch.setattr(manager, "_bootstrap_douyin", bootstrap)
    url = "https://www.douyin.com/video/7636370662940085510"

    first = await manager.ensure("douyin", url)
    second = await manager.ensure("douyin", url)
    forced = await manager.ensure("douyin", url, force=True)

    assert first is second
    assert forced == first
    assert bootstrap.call_count == 2
