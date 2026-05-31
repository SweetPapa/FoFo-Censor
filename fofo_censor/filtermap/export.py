"""Shareable (content-free) filter-map export (design §7.1).

Strips the local-only audit fields — the literal censored `word`, the visual
`description`, and local `tts_clip` paths — leaving only timestamps, categories,
styles, and actions. This is the legally clean, Phase-2-safe unit of reuse.
"""

from __future__ import annotations

import copy

from .schema import FilterMap


def to_shareable(fmap: FilterMap) -> dict:
    """Return a JSON-able dict with all local-only fields removed."""
    data = copy.deepcopy(fmap.model_dump())

    # Drop the full transcript (it contains the spoken words verbatim).
    data.pop("transcript", None)

    for edit in data.get("audio_edits", []):
        edit.pop("word", None)
        edit.pop("tts_clip", None)

    for edit in data.get("visual_edits", []):
        edit.pop("tts_clip", None)
        if isinstance(edit.get("detected"), dict):
            edit["detected"].pop("description", None)

    return data
