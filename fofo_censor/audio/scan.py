"""Holistic full-transcript scan via the model (design §6.2 step 4, extended).

Stage-1 (`decision.build_audio_edits`) only catches words that are in a wordlist.
This pass sends the *entire* transcript to the model and asks it to flag any
objectionable word it finds — profanity, slurs, sexual terms — regardless of
whether the word is on a list. It exists because a curated list can never be
exhaustive; whenever the model endpoint is available this should run so nothing
slips through just for being unlisted.

The hard part is mapping the model's findings back to exact timestamps. We send
the transcript as *indexed* tokens and ask the model to return those indices.
Each returned index is then verified against the word text it claims to be: if
`transcript[index]` doesn't match, we search the same chunk for the word before
giving up. This keeps a hallucinated or off-by-one index from censoring the
wrong moment.

Batched JSON contract:
    { "flagged": [ { "index", "word", "category", "tier" } ] }
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib import resources
from typing import Optional

from ..filtermap.schema import WordToken
from ..model import ModelClient, ModelError
from .classify import normalize

log = logging.getLogger("fofo_censor.scan")

# Words per model call. Small enough to keep outputs reliable, with a little
# overlap so a word at a chunk boundary still has context on both sides.
DEFAULT_CHUNK_SIZE = 300
DEFAULT_OVERLAP = 20

_VALID_CATEGORIES = ("profanity", "slur", "sexual_term")
_VALID_TIERS = ("mild", "moderate", "severe")


@dataclass
class ScanHit:
    index: int
    word: str
    category: str
    tier: str


def _prompt() -> str:
    return resources.files("fofo_censor.prompts").joinpath(
        "audio_scan.v1.txt"
    ).read_text(encoding="utf-8")


def scan_transcript(
    transcript: list[WordToken],
    *,
    client: ModelClient,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[ScanHit]:
    """Scan the whole transcript and return verified objectionable hits.

    Hits are de-duplicated by token index (overlapping chunks can surface the
    same word twice). A batch that errors is logged and skipped so the rest of
    the transcript is still scanned (graceful degradation, §13a).
    """
    if not transcript:
        return []

    system = _prompt()
    n = len(transcript)
    step = max(1, chunk_size - overlap)
    hits_by_index: dict[int, ScanHit] = {}

    for start in range(0, n, step):
        end = min(n, start + chunk_size)
        window = range(start, end)
        items = [{"index": i, "word": transcript[i].word} for i in window]

        user = (
            "Scan these transcript words and flag the objectionable ones. Return "
            'a JSON object {"flagged": [ ... ]} using the contract.\n\n'
            f"WORDS:\n{_dumps(items)}"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        try:
            raw = client.chat_json(messages, enable_thinking=False)
        except ModelError as exc:
            log.warning("Scan chunk [%d:%d] dropped: %s", start, end, exc)
            if end >= n:
                break
            continue

        for entry in _coerce_flagged(raw):
            hit = _resolve_hit(entry, transcript, start, end)
            if hit is not None:
                hits_by_index[hit.index] = hit

        if end >= n:
            break

    return [hits_by_index[i] for i in sorted(hits_by_index)]


def _resolve_hit(
    entry: dict, transcript: list[WordToken], lo: int, hi: int
) -> Optional[ScanHit]:
    """Map one model result to a verified token index, or None if it can't be."""
    claimed_word = normalize(str(entry.get("word", "")))
    category = entry.get("category") if entry.get("category") in _VALID_CATEGORIES else "profanity"
    tier = entry.get("tier") if entry.get("tier") in _VALID_TIERS else "moderate"

    raw_index = entry.get("index")
    index: Optional[int] = raw_index if isinstance(raw_index, int) else None

    # Trust the index only if it lands in this chunk and the word agrees (or the
    # model gave no word to check against).
    if index is not None and lo <= index < hi:
        if not claimed_word or normalize(transcript[index].word) == claimed_word:
            return ScanHit(index, transcript[index].word, category, tier)

    # Index was wrong/missing but we have a word: find it within the chunk.
    if claimed_word:
        for i in range(lo, hi):
            if normalize(transcript[i].word) == claimed_word:
                return ScanHit(i, transcript[i].word, category, tier)
        log.debug("Scan hit %r not localizable in chunk [%d:%d]; skipping.",
                  entry.get("word"), lo, hi)

    return None


def _dumps(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


def _coerce_flagged(raw) -> list[dict]:
    """Accept {"flagged": [...]}, a bare list, or a single object."""
    if isinstance(raw, dict):
        for key in ("flagged", "results", "items"):
            if isinstance(raw.get(key), list):
                return [x for x in raw[key] if isinstance(x, dict)]
        if "index" in raw or "word" in raw:
            return [raw]
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []
