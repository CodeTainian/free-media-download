from __future__ import annotations

import asyncio
import json
import os
import platform as host_platform
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from .config import Settings


class BrowserSessionError(RuntimeError):
    pass


class BrowserUnavailableError(BrowserSessionError):
    pass


@dataclass(frozen=True, slots=True)
class BrowserSession:
    cookies_file: Path
    user_agent: str
    expires_at: float


class AnonymousBrowserSessionManager:
    _DOUYIN_REQUIRED_COOKIES = frozenset(
        {"s_v_web_id", "ttwid", "__ac_nonce", "__ac_signature", "odin_tt", "UIFID"}
    )

    def __init__(self, config: Settings):
        self.config = config
        self._session: BrowserSession | None = None
        self._lock = asyncio.Lock()
        self._cookies_file = config.data_dir / ".browser-sessions" / "douyin.cookies.txt"

    def available(self) -> bool:
        try:
            self._find_browser()
        except BrowserUnavailableError:
            return False
        return True

    async def ensure(self, platform: str, url: str, force: bool = False) -> BrowserSession | None:
        if not self.config.anonymous_browser_cookies or platform != "douyin":
            return None
        now = time.monotonic()
        if (
            not force
            and self._session
            and self._session.expires_at > now
            and self._session.cookies_file.is_file()
        ):
            return self._session
        async with self._lock:
            now = time.monotonic()
            if (
                not force
                and self._session
                and self._session.expires_at > now
                and self._session.cookies_file.is_file()
            ):
                return self._session
            session = await asyncio.to_thread(self._bootstrap_douyin, url)
            self._session = session
            return session

    async def close(self) -> None:
        async with self._lock:
            self._session = None
            self._cookies_file.unlink(missing_ok=True)

    def _bootstrap_douyin(self, url: str) -> BrowserSession:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"douyin.com", "www.douyin.com"}
            or not re.fullmatch(r"/video/[0-9]{10,30}", parsed.path)
        ):
            raise BrowserSessionError("The anonymous browser received an invalid Douyin video URL.")

        browser = self._find_browser()
        user_agent = self._browser_user_agent(browser)
        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            debug_port = int(port_socket.getsockname()[1])

        process: subprocess.Popen[bytes] | None = None
        try:
            with tempfile.TemporaryDirectory(prefix="savebolt-browser-") as profile:
                try:
                    command = [
                        browser,
                        "--headless=new",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--no-first-run",
                        "--no-default-browser-check",
                        f"--remote-debugging-port={debug_port}",
                        "--remote-allow-origins=*",
                        f"--user-data-dir={profile}",
                        f"--user-agent={user_agent}",
                    ]
                    if self.config.browser_no_sandbox:
                        command.append("--no-sandbox")
                    proxy = (
                        self.config.yt_dlp_proxy
                        or os.getenv("HTTPS_PROXY")
                        or os.getenv("https_proxy")
                    )
                    if proxy:
                        command.append(f"--proxy-server={proxy}")
                    command.append(url)
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    page = self._wait_for_page(debug_port)
                    douyin_cookies = self._wait_for_douyin_cookies(page)
                    self._write_cookie_file(douyin_cookies)
                finally:
                    if process is not None:
                        self._terminate(process)
        except BrowserSessionError:
            raise
        except (OSError, subprocess.SubprocessError, TimeoutError, ValueError) as exc:
            raise BrowserSessionError("The anonymous browser session could not be created.") from exc

        return BrowserSession(
            cookies_file=self._cookies_file,
            user_agent=user_agent,
            expires_at=time.monotonic() + max(60, self.config.browser_session_ttl_seconds),
        )

    def _find_browser(self) -> str:
        candidates = [
            self.config.browser_binary,
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
            shutil.which("google-chrome"),
            shutil.which("google-chrome-stable"),
            shutil.which("chrome"),
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        raise BrowserUnavailableError("No supported Chromium browser is installed for anonymous sessions.")

    def _browser_user_agent(self, browser: str) -> str:
        try:
            result = subprocess.run(
                [browser, "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BrowserUnavailableError("The configured Chromium browser could not be started.") from exc
        match = re.search(r"([0-9]+(?:\.[0-9]+){1,3})", result.stdout or result.stderr)
        if not match:
            raise BrowserUnavailableError("The configured Chromium version could not be detected.")
        system = (
            "Macintosh; Intel Mac OS X 10_15_7"
            if host_platform.system() == "Darwin"
            else "X11; Linux x86_64"
        )
        return (
            f"Mozilla/5.0 ({system}) AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{match.group(1)} Safari/537.36"
        )

    def _wait_for_page(self, debug_port: int) -> dict[str, object]:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + max(5, self.config.browser_start_timeout_seconds)
        endpoint = f"http://127.0.0.1:{debug_port}/json"
        while time.monotonic() < deadline:
            try:
                with opener.open(endpoint, timeout=1) as response:
                    pages = json.load(response)
                page = next(
                    (
                        item
                        for item in pages
                        if isinstance(item, dict)
                        and item.get("type") == "page"
                        and isinstance(item.get("webSocketDebuggerUrl"), str)
                    ),
                    None,
                )
                if page:
                    return page
            except (OSError, ValueError):
                pass
            time.sleep(0.25)
        raise BrowserSessionError("The anonymous browser did not become ready in time.")

    def _read_cookies(self, page: dict[str, object]) -> list[dict[str, object]]:
        try:
            with connect(
                str(page["webSocketDebuggerUrl"]),
                origin="http://localhost",
                proxy=None,
                open_timeout=5,
            ) as ws:
                ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
                response = None
                for _ in range(10):
                    candidate = json.loads(ws.recv(timeout=5))
                    if candidate.get("id") == 1:
                        response = candidate
                        break
                if response is None:
                    raise BrowserSessionError("The anonymous browser did not return its cookies.")
        except BrowserSessionError:
            raise
        except (KeyError, OSError, TimeoutError, ValueError, WebSocketException) as exc:
            raise BrowserSessionError("The anonymous browser cookies could not be read.") from exc
        cookies = response.get("result", {}).get("cookies", [])
        if not isinstance(cookies, list):
            raise BrowserSessionError("The anonymous browser returned an invalid cookie response.")
        return [cookie for cookie in cookies if isinstance(cookie, dict)]

    def _wait_for_douyin_cookies(self, page: dict[str, object]) -> list[dict[str, object]]:
        deadline = time.monotonic() + max(5, self.config.browser_cookie_wait_seconds)
        while time.monotonic() < deadline:
            cookies = self._read_cookies(page)
            douyin_cookies = [
                cookie
                for cookie in cookies
                if str(cookie.get("domain") or "").lstrip(".").endswith("douyin.com")
            ]
            cookie_names = {str(cookie.get("name") or "") for cookie in douyin_cookies}
            if self._DOUYIN_REQUIRED_COOKIES <= cookie_names:
                return douyin_cookies
            time.sleep(0.5)
        raise BrowserSessionError("Douyin did not issue the required anonymous session cookie.")

    def _write_cookie_file(self, cookies: list[dict[str, object]]) -> None:
        self._cookies_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lines = ["# Netscape HTTP Cookie File"]
        for cookie in cookies:
            domain = self._field(cookie.get("domain"))
            name = self._field(cookie.get("name"))
            if not domain or not name:
                continue
            lines.append(
                "\t".join(
                    [
                        domain,
                        "TRUE" if domain.startswith(".") else "FALSE",
                        self._field(cookie.get("path")) or "/",
                        "TRUE" if cookie.get("secure") else "FALSE",
                        str(max(0, int(cookie.get("expires") or 0))),
                        name,
                        self._field(cookie.get("value")),
                    ]
                )
            )
        temporary = self._cookies_file.with_suffix(".tmp")
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(self._cookies_file)

    @staticmethod
    def _field(value: object) -> str:
        return str(value or "").replace("\t", "").replace("\r", "").replace("\n", "")

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait()
