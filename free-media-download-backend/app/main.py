from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .audio_processor import AudioProcessor
from .analysis_exports import (
    export_json,
    export_markdown,
    export_website_zip,
)
from .analysis_jobs import AnalysisJobManager
from .analysis_models import (
    AnalysisResult,
    AnalysisSnapshot,
    ArtifactKind,
    ArtifactStatus,
    ArtifactView,
    CreateAnalysisRequest,
    CreateAnalysisResponse,
    RequestArtifactRequest,
    WebsiteManifest,
    WebsiteTheme,
)
from .analysis_provider import AnalysisError, DeepSeekAnalysisProvider
from .config import settings
from .downloader import DownloadError, YtDlpService, binary_available
from .frame_extractor import FrameExtractor
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
from .transcript_acquisition import TranscriptAcquisitionService
from .transcription_provider import build_transcription_provider
from .transcripts import SUMMARY_PLATFORMS
from .website_renderer import render_website_html


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


transcription_provider = build_transcription_provider(settings)
downloader = YtDlpService(
    settings, transcription_ready=transcription_provider.ready
)
jobs = JobManager(settings, downloader)
summary_service = SummaryService(settings, DeepSeekSummaryProvider(settings))
transcript_acquisition = TranscriptAcquisitionService(
    settings,
    downloader,
    AudioProcessor(settings),
    transcription_provider,
)
summaries = SummaryJobManager(settings, transcript_acquisition, summary_service)
analysis_provider = DeepSeekAnalysisProvider(settings)
analyses = AnalysisJobManager(
    settings,
    transcript_acquisition,
    analysis_provider,
    FrameExtractor(settings, downloader),
)
limiter = MemoryRateLimiter()


@asynccontextmanager
async def lifespan(_: FastAPI):
    jobs.start()
    summaries.start()
    analyses.start()
    yield
    await analyses.stop()
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


@app.exception_handler(AnalysisError)
async def analysis_error(_: Request, exc: AnalysisError):
    if exc.code == "ANALYSIS_RATE_LIMITED":
        status = 429
    elif exc.code == "ANALYSIS_PROVIDER_UNAVAILABLE":
        status = 503
    elif exc.code in {"ANALYSIS_NOT_READY", "ARTIFACT_NOT_READY"}:
        status = 409
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
        transcription=transcription_provider.ready(),
        transcription_provider=(
            settings.transcription_provider
            if settings.transcription_provider != "none"
            else None
        ),
        analysis=analysis_provider.ready(),
        analysis_provider=(
            analysis_provider.provider_name if analysis_provider.ready() else None
        ),
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


@app.post("/api/v1/analyses", response_model=CreateAnalysisResponse, status_code=201)
async def create_analysis(
    payload: CreateAnalysisRequest, request: Request
) -> CreateAnalysisResponse:
    platform, _ = classify_url(payload.url)
    if platform not in SUMMARY_PLATFORMS:
        raise AnalysisError(
            "ANALYSIS_UNSUPPORTED_PLATFORM",
            "Video knowledge analysis currently supports YouTube and Bilibili.",
        )
    if not analyses.ready():
        raise AnalysisError(
            "ANALYSIS_PROVIDER_UNAVAILABLE",
            "Content analysis is not configured on this server.",
            True,
        )
    if not limiter.check(
        client_key(request), "analysis", settings.summary_daily_limit, 24 * 60 * 60
    ):
        raise AnalysisError(
            "ANALYSIS_RATE_LIMITED",
            "This network has reached the daily video analysis limit.",
            True,
        )
    job = await analyses.create(payload)
    return CreateAnalysisResponse(
        analysis=analyses.view(job),
        events_url=f"/api/v1/analyses/{job.id}/events",
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


@app.get(
    "/api/v1/analyses/{analysis_id}",
    response_model=AnalysisSnapshot,
)
async def get_analysis(analysis_id: str) -> AnalysisSnapshot:
    job = analyses.get(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analyses.view(job)


@app.get("/api/v1/analyses/{analysis_id}/result", response_model=AnalysisResult)
async def get_analysis_result(analysis_id: str) -> AnalysisResult:
    job = analyses.get(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis not found")
    result = analyses.result(job)
    if not result:
        raise AnalysisError(
            "ANALYSIS_NOT_READY",
            "The canonical analysis is not ready yet.",
            True,
        )
    return result


@app.post(
    "/api/v1/analyses/{analysis_id}/artifacts",
    response_model=ArtifactView,
    status_code=202,
)
async def request_analysis_artifact(
    analysis_id: str, payload: RequestArtifactRequest
) -> ArtifactView:
    job = analyses.get(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis not found")
    artifact = await analyses.request_artifact(job, ArtifactKind(payload.kind))
    return analyses.artifact_view(artifact)


@app.get("/api/v1/analyses/{analysis_id}/artifacts/{kind}")
async def get_analysis_artifact(analysis_id: str, kind: ArtifactKind):
    job = analyses.get(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis not found")
    artifact = job.artifacts[kind]
    if artifact.status != ArtifactStatus.COMPLETED or artifact.payload is None:
        raise AnalysisError(
            "ARTIFACT_NOT_READY",
            "This knowledge artifact is not ready yet.",
            artifact.status in {ArtifactStatus.QUEUED, ArtifactStatus.RUNNING},
        )
    payload = artifact.payload
    if isinstance(payload, list):
        return [item.model_dump(mode="json") for item in payload]
    return payload.model_dump(mode="json")


@app.get("/api/v1/analyses/{analysis_id}/frames/{frame_id}")
async def get_analysis_frame(analysis_id: str, frame_id: str):
    job = analyses.get(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis not found")
    path = job.frame_paths.get(frame_id)
    if (
        not path
        or not path.is_file()
        or not path.resolve().is_relative_to(job.directory.resolve())
    ):
        raise HTTPException(status_code=404, detail="Frame not found")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/v1/analyses/{analysis_id}/artifacts/{kind}/export")
async def export_analysis_artifact(
    analysis_id: str,
    kind: ArtifactKind,
    format: Literal["json", "markdown", "html", "zip"] = Query("json"),
    theme: WebsiteTheme | None = Query(None),
):
    job = analyses.get(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis not found")
    artifact = job.artifacts[kind]
    if artifact.status != ArtifactStatus.COMPLETED or artifact.payload is None:
        raise AnalysisError(
            "ARTIFACT_NOT_READY",
            "This knowledge artifact is not ready yet.",
            True,
        )
    payload = artifact.payload
    filename = f"bubble-{kind.value}"
    if format == "json":
        body = export_json(payload)
        return Response(
            body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}.json"'},
        )
    if format == "markdown":
        body = export_markdown(kind, payload)
        return Response(
            body,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}.md"'},
        )
    if kind != ArtifactKind.DYNAMIC_WEBSITE or not isinstance(
        payload, WebsiteManifest
    ):
        raise AnalysisError(
            "EXPORT_UNSUPPORTED",
            "This export format is only available for Dynamic Website.",
        )
    if format == "html":
        return Response(
            render_website_html(payload, theme=theme),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="index.html"'},
        )
    return Response(
        export_website_zip(payload, theme=theme),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="bubble-website.zip"'},
    )


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


@app.get("/api/v1/analyses/{analysis_id}/events")
async def analysis_events(analysis_id: str, request: Request):
    job = analyses.get(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis not found")
    last_id = request.headers.get("Last-Event-ID", "0")
    after = int(last_id) if last_id.isdigit() else 0
    return StreamingResponse(
        analyses.stream(job, after),
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


@app.post("/api/v1/analyses/{analysis_id}/cancel", status_code=204)
async def cancel_analysis(analysis_id: str):
    if not await analyses.cancel(analysis_id):
        raise HTTPException(status_code=404, detail="Analysis not found")
    return None


@app.delete("/api/v1/analyses/{analysis_id}", status_code=204)
async def delete_analysis(analysis_id: str):
    if not await analyses.delete(analysis_id):
        raise HTTPException(status_code=404, detail="Analysis not found")
    return None
