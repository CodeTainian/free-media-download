import asyncio

import pytest

from app.config import Settings
from app.downloader import DownloadError, YtDlpService, _normalize_info
from app.transcripts import (
    CaptionTrack,
    caption_languages,
    discover_caption_tracks,
    parse_subtitle_file,
    parse_subtitle_text,
    select_caption_track,
)


def caption_info() -> dict[str, object]:
    return {
        "language": "zh-Hans",
        "subtitles": {
            "zh-Hans": [{"ext": "srt", "url": "https://signed.example/zh"}],
            "live_chat": [{"ext": "json", "url": "https://signed.example/chat"}],
            "danmaku": [{"ext": "xml", "url": "https://signed.example/danmaku"}],
        },
        "automatic_captions": {
            "en-US": [{"ext": "vtt", "url": "https://signed.example/en"}],
            "zh-Hans": [{"ext": "vtt", "url": "https://signed.example/auto-zh"}],
        },
    }


def test_discovers_safe_caption_metadata_without_urls_or_comments():
    info = caption_info()
    tracks = discover_caption_tracks(info)

    assert [(track.language, track.automatic) for track in tracks] == [
        ("zh-Hans", False),
        ("en-US", True),
        ("zh-Hans", True),
    ]
    assert caption_languages(info) == ["zh-Hans", "en-US"]
    assert all(not hasattr(track, "url") for track in tracks)


def test_caption_selection_uses_required_manual_and_language_priority():
    info = caption_info()
    assert select_caption_track(info) == CaptionTrack(language="zh-Hans", automatic=False)

    subtitles = info["subtitles"]
    assert isinstance(subtitles, dict)
    subtitles["en"] = [{"ext": "vtt", "url": "https://signed.example/manual-en"}]
    assert select_caption_track(info) == CaptionTrack(language="en", automatic=False)


def test_caption_selection_prefers_english_auto_when_original_manual_is_missing():
    info = caption_info()
    info["subtitles"] = {"fr": [{"ext": "vtt"}]}
    info["language"] = "zh-Hans"

    assert select_caption_track(info) == CaptionTrack(language="en-US", automatic=True)


def test_caption_selection_chooses_translation_from_declared_original_language():
    info = {
        "language": "zh-Hans",
        "automatic_captions": {
            "en-sq": [{"ext": "vtt"}],
            "en-zh-Hans": [{"ext": "vtt"}],
            "zh-Hans": [{"ext": "vtt"}],
        },
    }

    assert select_caption_track(info) == CaptionTrack(language="en-zh-Hans", automatic=True)


def test_public_caption_language_list_is_bounded_and_prioritizes_english():
    info = {
        "language": "zh",
        "automatic_captions": {
            **{f"lang{index}-zh": [{"ext": "vtt"}] for index in range(100)},
            "en-zh": [{"ext": "vtt"}],
            "zh": [{"ext": "vtt"}],
        },
    }

    languages = caption_languages(info)
    assert len(languages) == 64
    assert languages[:2] == ["en-zh", "zh"]


def test_vtt_parser_cleans_markup_deduplicates_rollups_and_removes_overlap():
    segments = parse_subtitle_text(
        """WEBVTT

00:00:00.000 --> 00:00:02.000 align:start
<c>Hello &amp; welcome</c>

00:00:01.500 --> 00:00:03.500
Hello &amp; welcome everyone

00:00:03.500 --> 00:00:04.000
&lt;script&gt;alert(1)&lt;/script&gt; Useful point

00:00:04.000 --> 00:00:05.000
Useful point
"""
    )

    assert [(item.id, item.start, item.end, item.text) for item in segments] == [
        ("seg-00001", 0.0, 2.0, "Hello & welcome"),
        ("seg-00002", 2.0, 3.5, "everyone"),
        ("seg-00003", 3.5, 4.0, "alert(1) Useful point"),
        ("seg-00004", 4.0, 5.0, "Useful point"),
    ]
    assert all(left.end <= right.start for left, right in zip(segments, segments[1:]))


def test_srt_parser_discards_invalid_cues_and_supports_comma_timestamps(tmp_path):
    subtitle = tmp_path / "sample.srt"
    subtitle.write_text(
        """1
00:00:01,250 --> 00:00:02,500
{\\an8}<b>First line</b>

2
00:00:04,000 --> 00:00:03,000
Invalid range

3
00:00:02,500 --> 00:00:03,250
Second line
""",
        encoding="utf-8",
    )

    segments = parse_subtitle_file(subtitle)
    assert [(item.start, item.end, item.text) for item in segments] == [
        (1.25, 2.5, "First line"),
        (2.5, 3.25, "Second line"),
    ]


def test_probe_metadata_marks_only_supported_platforms_with_captions():
    info = caption_info() | {"title": "Lesson", "formats": []}

    youtube = _normalize_info(info, "https://youtu.be/public", platform_key="youtube")
    vimeo = _normalize_info(info, "https://vimeo.com/public", platform_key="vimeo")

    assert youtube.summary_supported is True
    assert youtube.caption_languages == ["zh-Hans", "en-US"]
    assert youtube.transcript_strategy_hint == "captions"
    assert vimeo.summary_supported is False
    assert vimeo.caption_languages == []
    assert vimeo.transcript_strategy_hint == "unsupported"


def test_probe_metadata_marks_supported_video_without_captions_unavailable():
    media = _normalize_info(
        {"title": "Silent lesson", "formats": []},
        "https://www.youtube.com/watch?v=public",
        platform_key="youtube",
    )

    assert media.summary_supported is False
    assert media.transcript_strategy_hint == "unavailable"


def test_caption_command_uses_fixed_output_and_selected_track(tmp_path):
    service = YtDlpService(Settings(data_dir=tmp_path, yt_dlp_binary="yt-dlp-test"))
    command = service._caption_download_command(
        "https://www.youtube.com/watch?v=public",
        tmp_path,
        CaptionTrack(language="en-US", automatic=True),
        ["--proxy", "http://127.0.0.1:8080"],
    )

    assert command[0] == "yt-dlp-test"
    assert "--no-playlist" in command
    assert "--write-auto-subs" in command
    assert "--write-subs" not in command
    assert command[command.index("--sub-langs") + 1] == "en-US"
    assert command[command.index("--sub-format") + 1] == "vtt/srt"
    assert "https://signed.example/en" not in command
    assert command[-1] == "https://www.youtube.com/watch?v=public"


@pytest.mark.asyncio
async def test_fetch_caption_transcript_returns_normalized_document(tmp_path, monkeypatch):
    service = YtDlpService(Settings(data_dir=tmp_path))
    info = caption_info() | {
        "title": "Public lesson",
        "duration": 120,
        "webpage_url": "https://www.youtube.com/watch?v=public",
    }

    async def fake_payload(_platform, _normalized):
        return info

    async def fake_download(_platform, _normalized, output_dir, track, _cancel_event):
        assert track == CaptionTrack(language="zh-Hans", automatic=False)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "savebolt-caption.zh-Hans.vtt"
        path.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n知识点\n", encoding="utf-8")
        return path

    monkeypatch.setattr(service, "_load_platform_payload", fake_payload)
    monkeypatch.setattr(service, "_download_caption_file", fake_download)

    transcript = await service.fetch_caption_transcript(
        "https://www.youtube.com/watch?v=public", tmp_path / "captions", cancel_event=asyncio.Event()
    )

    assert transcript.title == "Public lesson"
    assert transcript.language == "zh-Hans"
    assert transcript.source_kind == "manual_caption"
    assert transcript.segments[0].text == "知识点"


@pytest.mark.asyncio
async def test_fetch_caption_transcript_rejects_missing_captions(tmp_path, monkeypatch):
    service = YtDlpService(Settings(data_dir=tmp_path))

    async def fake_payload(_platform, _normalized):
        return {"title": "No captions", "duration": 30}

    monkeypatch.setattr(service, "_load_platform_payload", fake_payload)
    with pytest.raises(DownloadError) as caught:
        await service.fetch_caption_transcript(
            "https://www.bilibili.com/video/BV1public", tmp_path / "captions"
        )
    assert caught.value.code == "NO_CAPTIONS"


@pytest.mark.asyncio
async def test_fetch_caption_transcript_enforces_platform_and_two_hour_limit(tmp_path, monkeypatch):
    service = YtDlpService(Settings(data_dir=tmp_path, summary_max_duration_seconds=7200))
    with pytest.raises(DownloadError) as unsupported:
        await service.fetch_caption_transcript("https://vimeo.com/123", tmp_path / "vimeo")
    assert unsupported.value.code == "SUMMARY_UNSUPPORTED_PLATFORM"

    async def fake_payload(_platform, _normalized):
        return caption_info() | {"duration": 7201}

    monkeypatch.setattr(service, "_load_platform_payload", fake_payload)
    with pytest.raises(DownloadError) as too_long:
        await service.fetch_caption_transcript(
            "https://www.youtube.com/watch?v=public", tmp_path / "youtube"
        )
    assert too_long.value.code == "MEDIA_TOO_LONG"
