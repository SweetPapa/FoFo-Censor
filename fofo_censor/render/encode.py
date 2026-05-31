"""Export encoding settings (design §10a).

Maps a profile's `render` block to ffmpeg video-encoder arguments. The fast
audio-only path (`beep.render`) stream-copies video; the disclaimer/concat path
(`pipeline.render`) must re-encode, and uses these flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_VIDEO_CODECS = {
    "hevc": {"software": "libx265", "nvenc": "hevc_nvenc"},
    "av1": {"software": "libsvtav1", "nvenc": "av1_nvenc"},
    "h264": {"software": "libx264", "nvenc": "h264_nvenc"},
}


@dataclass
class RenderSettings:
    # Default to H.264/software for broad compatibility and reasonable speed.
    # The design's `efficient` default is HEVC; profiles opt into it explicitly.
    video_codec: str = "h264"
    encoder: str = "software"
    quality: int = 20
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"

    @classmethod
    def from_profile_block(cls, block: Optional[dict]) -> "RenderSettings":
        if not block:
            return cls()
        return cls(
            video_codec=block.get("video_codec", cls.video_codec),
            encoder=block.get("encoder", cls.encoder),
            quality=int(block.get("quality", cls.quality)),
            audio_codec=block.get("audio_codec", cls.audio_codec),
            audio_bitrate=block.get("audio_bitrate", cls.audio_bitrate),
        )


def video_encoder_args(codec: str = "h264", encoder: str = "software",
                       quality: int = 20) -> list[str]:
    """Return ffmpeg `-c:v ... -crf/-cq ...` args for the given render settings."""
    table = _VIDEO_CODECS.get(codec)
    if table is None:
        raise ValueError(f"Unsupported video codec: {codec}")
    enc = table.get(encoder)
    if enc is None:
        raise ValueError(f"Unsupported codec/encoder combo: {codec}/{encoder}")
    quality_flag = "-cq" if encoder == "nvenc" else "-crf"
    return ["-c:v", enc, quality_flag, str(quality)]


def audio_encoder_args(settings: RenderSettings) -> list[str]:
    return ["-c:a", settings.audio_codec, "-b:a", settings.audio_bitrate]
