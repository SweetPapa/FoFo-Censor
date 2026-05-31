"""Stage-2 contextual disambiguation via the model (design §6.2 step 4, §7.4).

STUB. Handles homographs ("ass" the insult vs. the animal), list-boundary /
low-confidence words, and a holistic whole-transcript pass that tags
meaning-bearing segments so the renderer never escalates a word edit into a cut.
Slurs are never un-flagged.

Batched JSON contract (§7.4):
    [ { "word_id", "is_objectionable", "category", "tier", "meaning_bearing" } ]
"""

from __future__ import annotations

from typing import Optional

from ..filtermap.schema import WordToken
from ..model import ModelClient


def disambiguate(
    candidates: list[WordToken],
    *,
    client: Optional[ModelClient] = None,
) -> list[dict]:
    """Return per-word objectionability decisions. Not implemented yet."""
    raise NotImplementedError(
        "Stage-2 audio disambiguation (M4) is not implemented. "
        "Batch candidates to ModelClient.chat_json with enable_thinking=False."
    )
