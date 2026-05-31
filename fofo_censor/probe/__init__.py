"""ffprobe / ffmpeg discovery and media probing (design §6.1)."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass

from .fingerprint import fingerprint_file

__all__ = ["MediaInfo", "probe", "require_tool", "FFmpegNotFound", "fingerprint_file"]


class FFmpegNotFound(RuntimeError):
    pass


def require_tool(name: str) -> str:
    """Return the path to an ffmpeg-family tool or raise a clear error."""
    path = shutil.which(name)
    if not path:
        raise FFmpegNotFound(
            f"'{name}' was not found on PATH. Install ffmpeg "
            "(macOS: `brew install ffmpeg`, Debian/Ubuntu: `apt install ffmpeg`, "
            "Windows: https://ffmpeg.org/download.html)."
        )
    return path


@dataclass
class MediaInfo:
    duration_sec: float
    has_video: bool
    has_audio: bool
    audio_track_count: int
    width: int = 0
    height: int = 0
    fps: float = 0.0


def _parse_fps(rate: str) -> float:
    try:
        num, den = rate.split("/")
        den_f = float(den)
        return float(num) / den_f if den_f else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: str) -> MediaInfo:
    """Probe a media file with ffprobe."""
    ffprobe = require_tool("ffprobe")
    cmd = [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", path]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)

    streams = data.get("streams", [])
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    video_streams = [s for s in streams if s.get("codec_type") == "video"]

    fmt = data.get("format", {})
    duration = 0.0
    if "duration" in fmt:
        duration = float(fmt["duration"])
    elif audio_streams and "duration" in audio_streams[0]:
        duration = float(audio_streams[0]["duration"])

    width = height = 0
    fps = 0.0
    if video_streams:
        v = video_streams[0]
        width = int(v.get("width", 0) or 0)
        height = int(v.get("height", 0) or 0)
        fps = _parse_fps(v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/0")

    return MediaInfo(
        duration_sec=duration,
        has_video=bool(video_streams),
        has_audio=bool(audio_streams),
        audio_track_count=len(audio_streams),
        width=width,
        height=height,
        fps=fps,
    )
