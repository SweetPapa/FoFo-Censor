"""Safe-word replacement: text generation + window fitting (design §7a, M3).

STUB. Two responsibilities:

1. Generate clean replacement text for flagged `safe_replace` words, batched to
   the model with the surrounding line, profile `tone`, and `match_syllables`
   (§7.4 safe-word writer contract: [{ "word_id", "replacement" }]).
2. Fit a synthesized TTS clip into the original word's time window per
   `fit_strategy` (timestretch | pad | natural).

The TTS synthesis itself lives in `tts.kokoro`.
"""

from __future__ import annotations

from typing import Optional

from ..filtermap.schema import AudioEdit
from ..model import ModelClient


def generate_replacements(
    edits: list[AudioEdit],
    line_context: dict[str, str],
    *,
    tone: str = "comedic",
    match_syllables: bool = True,
    client: Optional[ModelClient] = None,
) -> dict[str, str]:
    """Map edit id -> replacement text. Not implemented yet."""
    raise NotImplementedError("Safe-word text generation (M3) is not implemented.")


def fit_clip_to_window(
    clip_path: str,
    start: float,
    end: float,
    *,
    fit_strategy: str = "natural",
    max_timestretch_pct: int = 25,
) -> str:
    """Produce a clip fitted to [start, end]. Returns a path. Not implemented yet."""
    raise NotImplementedError("Safe-word window fitting (M3) is not implemented.")
