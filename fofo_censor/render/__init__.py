"""Rendering: audio edits, disclaimer card, cutaway cards, encode (design §6.7, §10a, §12)."""

from .beep import default_output_path
from .disclaimer import compute_dwell, default_disclaimer_text
from .encode import RenderSettings
from .pipeline import render

__all__ = [
    "render",
    "default_output_path",
    "default_disclaimer_text",
    "compute_dwell",
    "RenderSettings",
]
