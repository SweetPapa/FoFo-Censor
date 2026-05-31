"""Disclaimer card prepended to every output (design §12).

Builds a black-slate card with centered, wrapped white text via ffmpeg
`drawtext`. The card is rendered as part of the single-pass concat in
`pipeline.py` (a generated card cannot be stream-copied in, per §10a), so this
module exposes the filtergraph fragment and the supporting helpers rather than
running ffmpeg itself.

The card is mandatory in v1 (legal posture, §12); only its wording and dwell are
configurable via the active profile.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Optional

# Font candidates by platform; first existing wins. If none exist we omit the
# fontfile and rely on ffmpeg's fontconfig default.
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",            # macOS
    "/System/Library/Fonts/Supplemental/Arial.ttf",   # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Debian/Ubuntu
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",         # Fedora
    "C:/Windows/Fonts/arial.ttf",                     # Windows
]


def default_disclaimer_text() -> str:
    return resources.files("fofo_censor.disclaimers").joinpath(
        "default.txt"
    ).read_text(encoding="utf-8").strip()


def find_font() -> Optional[str]:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return None


def compute_dwell(
    text: str,
    *,
    min_sec: float = 2.5,
    max_sec: float = 12.0,
    words_per_sec: float = 3.0,
) -> float:
    """Scale hold time to reading length, clamped to [min_sec, max_sec] (§12)."""
    words = max(1, len(text.split()))
    secs = 1.0 + words / words_per_sec
    return round(max(min_sec, min(max_sec, secs)), 2)


def _font_size(height: int) -> int:
    return max(16, height // 24)


def _wrap_columns(width: int, font_size: int) -> int:
    # Rough monospace-ish estimate: average glyph advance ~0.5em.
    return max(20, int(width / (font_size * 0.5)))


@dataclass
class CardFilter:
    """A disclaimer-card filtergraph fragment for the concat path."""

    parts: list[str]
    video_label: str
    audio_label: str
    dwell_sec: float


def write_wrapped_textfile(text: str, width: int, font_size: int, dest: Path) -> Path:
    """Wrap `text` to the frame width and write it for drawtext `textfile=`."""
    cols = _wrap_columns(width, font_size)
    wrapped_paragraphs = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        wrapped_paragraphs.append(textwrap.fill(para, width=cols))
    dest.write_text("\n\n".join(wrapped_paragraphs) + "\n", encoding="utf-8")
    return dest


def build_card_filter(
    text: str,
    *,
    width: int,
    height: int,
    fps: float,
    dwell_sec: float,
    textfile_path: str,
    sample_rate: int = 44100,
    video_label: str = "cardv",
    audio_label: str = "carda",
) -> CardFilter:
    """Build the black-slate card video+audio filtergraph fragment.

    `textfile_path` must already contain the wrapped card text (see
    `write_wrapped_textfile`).
    """
    fps_i = max(1, int(round(fps or 25)))
    font_size = _font_size(height)
    font = find_font()
    font_opt = f"fontfile='{font}':" if font else ""

    drawtext = (
        f"drawtext={font_opt}textfile='{textfile_path}':"
        f"fontcolor=white:fontsize={font_size}:line_spacing={max(4, font_size // 3)}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2"
    )

    video = (
        f"color=c=black:s={width}x{height}:r={fps_i}:d={dwell_sec:.3f},"
        f"format=yuv420p,setsar=1,{drawtext}[{video_label}]"
    )
    audio = (
        f"anullsrc=channel_layout=stereo:sample_rate={sample_rate},"
        f"atrim=0:{dwell_sec:.3f},asetpts=PTS-STARTPTS[{audio_label}]"
    )

    return CardFilter(
        parts=[video, audio],
        video_label=video_label,
        audio_label=audio_label,
        dwell_sec=dwell_sec,
    )
