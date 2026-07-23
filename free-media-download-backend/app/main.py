from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .downloader import DownloadError, YtDlpService, binary_available
from .jobs import JobManager
from .models import (
    CreateJobRequest,
    CreateJobResponse,
    CreateSummaryRequest,
    CreateSummaryResponse,
    ErrorBody,
    HealthResponse,
    JobView,
    ProbeRequest,
    ProbeResponse,
    SummaryJobView,
)
from .security import UnsafeUrlError, classify_url
from .summary_jobs import SummaryJobManager
from .summary_provider import DeepSeekSummaryProvider, SummaryError, SummaryService
from .transcripts import SUMMARY_PLATFORMS


class MemoryRateLimiter:
    def __init__(self) -> None:
        self.events: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, key: str, scope: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        bucket = self.events[(key, scope)]
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


downloader = YtDlpService(settings)
jobs = JobManager(settings, downloader)
summary_service = SummaryService(settings, DeepSeekSummaryProvider(settings))
summaries = SummaryJobManager(settings, downloader, summary_service)
limiter = MemoryRateLimiter()


@asynccontextmanager
async def lifespan(_: FastAPI):
    jobs.start()
    summaries.start()
    yield
    await summaries.stop()
    await jobs.stop()
    await downloader.close()


app = FastAPI(
    title="SaveBolt API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Last-Event-ID"],
)


def error_response(status: int, code: str, message: str, retryable: bool = False, item_index: int | None = None):
    body = ErrorBody(code=code, message=message, retryable=retryable, itemIndex=item_index)
    return JSONResponse(status_code=status, content=body.model_dump(exclude_none=True))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    return error_response(422, "INVALID_REQUEST", "The request contains an invalid or missing value.")


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "The requested resource is unavailable."
    code = "NOT_FOUND" if exc.status_code == 404 else "REQUEST_FAILED"
    return error_response(exc.status_code, code, message)


@app.exception_handler(UnsafeUrlError)
async def unsafe_url_error(_: Request, exc: UnsafeUrlError):
    return error_response(400, "UNSAFE_URL", str(exc))


@app.exception_handler(DownloadError)
async def download_error(_: Request, exc: DownloadError):
    status = (
        503
        if exc.code
        in {
            "COOKIE_REQUIRED",
            "COOKIE_REFRESH_FAILED",
            "COOKIE_SOURCE_ERROR",
            "BROWSER_UNAVAILABLE",
            "IMPERSONATION_UNAVAILABLE",
            "PLATFORM_ACCESS_BLOCKED",
            "RUNTIME_UNAVAILABLE",
            "SERVICE_UNAVAILABLE",
            "YOUTUBE_BOT_CHECK",
        }
        else 422
    )
    return error_response(status, exc.code, exc.message, exc.retryable)


@app.exception_handler(SummaryError)
async def summary_error(_: Request, exc: SummaryError):
    if exc.code == "SUMMARY_RATE_LIMITED":
        status = 429
    elif exc.code == "SUMMARY_PROVIDER_UNAVAILABLE":
        status = 503
    else:
        status = 422
    return error_response(status, exc.code, exc.message, exc.retryable)


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def command_output(command: list[str]) -> str | None:
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=4)
        if process.returncode == 0:
            return stdout.decode("utf-8", "replace")
    except (FileNotFoundError, TimeoutError):
        return None
    return None


def impersonation_target_available(output: str | None, target: str | None) -> bool:
    if not target:
        return True
    if not output:
        return False
    client = target.split(":", 1)[0].lower()
    return any(
        fields
        and fields[0].startswith(client)
        and "unavailable" not in line.lower()
        for line in output.splitlines()
        if (fields := line.lower().split())
    )


@app.get("/api/v1/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    yt_ready = binary_available(settings.yt_dlp_binary)
    ffmpeg_ready = binary_available(settings.ffmpeg_binary)
    javascript_ready = binary_available(settings.yt_dlp_js_runtime.split(":", 1)[0])
    browser_ready = downloader.anonymous_browser_available()
    version_output = (
        await command_output([settings.yt_dlp_binary, "--version"]) if yt_ready else None
    )
    impersonation_output = (
        await command_output([settings.yt_dlp_binary, "--list-impersonate-targets"])
        if yt_ready and settings.anonymous_browser_cookies
        else None
    )
    impersonation_ready = impersonation_target_available(
        impersonation_output, settings.browser_impersonate
    )
    version = version_output.splitlines()[0][:120] if version_output else None
    return HealthResponse(
        status=(
            "ok"
            if yt_ready
            and ffmpeg_ready
            and javascript_ready
            and (browser_ready or not settings.anonymous_browser_cookies)
            and (impersonation_ready or not settings.anonymous_browser_cookies)
            else "degraded"
        ),
        api=True,
        yt_dlp=yt_ready,
        ffmpeg=ffmpeg_ready,
        javascript_runtime=javascript_ready,
        anonymous_browser=browser_ready,
        request_impersonation=impersonation_ready,
        yt_dlp_version=version,
    )


@app.post("/api/v1/media/probe", response_model=ProbeResponse)
async def probe(payload: ProbeRequest, request: Request) -> ProbeResponse:
    if not limiter.check(client_key(request), "probe", 20, 15 * 60):
        raise DownloadError("RATE_LIMITED", "Too many links were analyzed. Please wait a few minutes.", True)
    return await downloader.probe(payload.url)


@app.post("/api/v1/jobs", response_model=CreateJobResponse, status_code=201)
async def create_job(payload: CreateJobRequest, request: Request) -> CreateJobResponse:
    if len(payload.items) > settings.max_batch_items:
        raise HTTPException(status_code=422, detail="Too many items")
    if not limiter.check(client_key(request), "job", 5, 60 * 60):
        raise DownloadError("RATE_LIMITED", "Too many download jobs were created. Please try again later.", True)
    for index, item in enumerate(payload.items):
        try:
            platform, _ = classify_url(item.url)
            if platform == "direct" and item.preset_id != "original":
                raise UnsafeUrlError("Public media file links must use the original file preset.")
            if platform != "direct" and item.preset_id == "original":
                raise UnsafeUrlError("Platform links require a video or audio preset.")
        except UnsafeUrlError as exc:
            return error_response(400, "UNSAFE_URL", str(exc), item_index=index)
    job = await jobs.create(payload.items, payload.bundle)
    return CreateJobResponse(job=jobs.view(job), events_url=f"/api/v1/jobs/{job.id}/events")


@app.post("/api/v1/summaries", response_model=CreateSummaryResponse, status_code=201)
async def create_summary(
    payload: CreateSummaryRequest, request: Request
) -> CreateSummaryResponse:
    platform, _ = classify_url(payload.url)
    if platform not in SUMMARY_PLATFORMS:
        raise SummaryError(
            "SUMMARY_UNSUPPORTED_PLATFORM",
            "AI summaries currently support YouTube and Bilibili videos.",
        )
    if not summaries.ready():
        raise SummaryError(
            "SUMMARY_PROVIDER_UNAVAILABLE",
            "AI summaries are not configured on this server.",
            True,
        )
    if not limiter.check(
        client_key(request), "summary", settings.summary_daily_limit, 24 * 60 * 60
    ):
        raise SummaryError(
            "SUMMARY_RATE_LIMITED",
            "This network has reached the daily AI summary limit.",
            True,
        )
    job = await summaries.create(payload)
    return CreateSummaryResponse(
        summary=summaries.view(job),
        events_url=f"/api/v1/summaries/{job.id}/events",
    )


@app.get("/api/v1/jobs/{job_id}", response_model=JobView)
async def get_job(job_id: str) -> JobView:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs.view(job)


@app.get("/api/v1/summaries/{summary_id}", response_model=SummaryJobView)
async def get_summary(summary_id: str) -> SummaryJobView:
    summary = summaries.get(summary_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    return summaries.view(summary)


@app.get("/api/v1/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    last_id = request.headers.get("Last-Event-ID", "0")
    after = int(last_id) if last_id.isdigit() else 0
    return StreamingResponse(
        jobs.stream(job, after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/v1/summaries/{summary_id}/events")
async def summary_events(summary_id: str, request: Request):
    summary = summaries.get(summary_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    last_id = request.headers.get("Last-Event-ID", "0")
    after = int(last_id) if last_id.isdigit() else 0
    return StreamingResponse(
        summaries.stream(summary, after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/v1/jobs/{job_id}/files/{item_id}")
async def download_file(job_id: str, item_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    item = next((candidate for candidate in job.items if candidate.id == item_id), None)
    if not item or not item.path or not item.path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if not item.path.resolve().is_relative_to(job.directory.resolve()):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(item.path, filename=item.path.name, media_type="application/octet-stream")


@app.get("/api/v1/jobs/{job_id}/bundle")
async def download_bundle(job_id: str):
    job = jobs.get(job_id)
    if not job or not job.bundle_path or not job.bundle_path.is_file():
        raise HTTPException(status_code=404, detail="Bundle not ready")
    return FileResponse(job.bundle_path, filename="savebolt-downloads.zip", media_type="application/zip")


@app.delete("/api/v1/jobs/{job_id}", status_code=204)
async def cancel_job(job_id: str):
    if not await jobs.cancel(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return None


@app.delete("/api/v1/summaries/{summary_id}", status_code=204)
async def cancel_summary(summary_id: str):
    if not await summaries.cancel(summary_id):
        raise HTTPException(status_code=404, detail="Summary not found")
    return None
