"""Decision engine: detections + profile -> typed filter-map edits (design §6.4, §8)."""

from .engine import build_audio_edits, build_disambiguated_edits, resolve_audio_style
from .coverage import compute_coverage

__all__ = [
    "build_audio_edits",
    "build_disambiguated_edits",
    "resolve_audio_style",
    "compute_coverage",
]
