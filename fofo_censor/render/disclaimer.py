"""Disclaimer card prepended to every output (design §12). STUB.

Renders a black-slate card (with optional Kokoro narration) and concatenates it
before the feature. `dwell_sec: auto` scales hold time to reading length. The
card is mandatory in v1 (legal posture); only its wording is editable.
"""

from __future__ import annotations

from importlib import resources
from typing import Optional


def default_disclaimer_text() -> str:
    return resources.files("fofo_censor.disclaimers").joinpath("default.txt").read_text(
        encoding="utf-8"
    )


def render_disclaimer_card(
    text: str,
    width: int,
    height: int,
    fps: float,
    out_path: str,
    *,
    dwell_sec: Optional[float] = None,
    narrate: bool = False,
) -> str:
    raise NotImplementedError(
        "Disclaimer card rendering is not implemented yet. Build a black slate "
        "with centered text via ffmpeg drawtext and prepend it (design §12)."
    )
