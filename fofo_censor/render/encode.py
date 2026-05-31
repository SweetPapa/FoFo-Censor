"""Export encoding settings (design §10a). STUB / helper.

Maps a profile's `render` block to ffmpeg encoder arguments. The current beep
renderer stream-copies video; once the disclaimer card and visual edits require a
full re-encode, this builds the codec/quality flags (HEVC default, AV1/H.264
options, NVENC vs software).
"""

from __future__ import annotations

_VIDEO_CODECS = {
    "hevc": {"software": "libx265", "nvenc": "hevc_nvenc"},
    "av1": {"software": "libsvtav1", "nvenc": "av1_nvenc"},
    "h264": {"software": "libx264", "nvenc": "h264_nvenc"},
}


def video_encoder_args(codec: str = "hevc", encoder: str = "software",
                       quality: int = 22) -> list[str]:
    """Return ffmpeg `-c:v ... -crf/-cq ...` args for the given render settings."""
    enc = _VIDEO_CODECS.get(codec, _VIDEO_CODECS["hevc"]).get(encoder)
    if enc is None:
        raise ValueError(f"Unsupported codec/encoder combo: {codec}/{encoder}")
    quality_flag = "-cq" if encoder == "nvenc" else "-crf"
    return ["-c:v", enc, quality_flag, str(quality)]
