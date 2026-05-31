"""Cutaway card rendering (design §6.7). STUB.

Replaces a flagged shot's video span with a generated card (black slate +
on-screen summary_text) and its audio with the Kokoro narration, then continues.
"""

from __future__ import annotations


def render_cutaway_card(
    summary_text: str,
    width: int,
    height: int,
    fps: float,
    duration_sec: float,
    out_path: str,
    *,
    narration_clip: str | None = None,
) -> str:
    raise NotImplementedError("Cutaway card rendering (M5) is not implemented.")
