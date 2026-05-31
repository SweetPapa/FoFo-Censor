"""Stage-2 contextual disambiguation via the model (design §6.2 step 4, §7.4, §8).

Stage-1 (`decision.build_audio_edits`) flags unambiguous wordlist hits and skips
entries marked `context_sensitive`. This module resolves those skipped homographs
("ass" the insult vs. the animal, "bloody" the intensifier vs. literal) by asking
the model, in context, whether each occurrence is actually objectionable.

Slurs are never routed here — they are always-flag at Stage-1 (§8), so a
context-sensitive entry of category "slur" is treated as objectionable without a
model call as a safety backstop.

Batched JSON contract (§7.4):
    [ { "word_id", "is_objectionable", "category", "tier", "meaning_bearing" } ]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib import resources

from ..filtermap.schema import WordToken
from ..model import ModelClient, ModelError
from .classify import Wordlist, WordlistEntry, normalize

log = logging.getLogger("fofo_censor.disambiguate")

DEFAULT_BATCH_SIZE = 40
DEFAULT_CONTEXT_WINDOW = 8


@dataclass
class Candidate:
    word_id: str
    index: int
    token: WordToken
    entry: WordlistEntry
    context: str


def _prompt() -> str:
    return resources.files("fofo_censor.prompts").joinpath(
        "audio_disambiguator.v1.txt"
    ).read_text(encoding="utf-8")


def build_context(transcript: list[WordToken], index: int, window: int) -> str:
    """A readable sentence around `index`, with the target word marked «like this»."""
    lo = max(0, index - window)
    hi = min(len(transcript), index + window + 1)
    parts = []
    for i in range(lo, hi):
        w = transcript[i].word
        parts.append(f"«{w}»" if i == index else w)
    return " ".join(parts)


def collect_candidates(
    transcript: list[WordToken],
    wordlist: Wordlist,
    *,
    context_window: int = DEFAULT_CONTEXT_WINDOW,
) -> list[Candidate]:
    """Find context-sensitive wordlist hits that need model disambiguation."""
    candidates: list[Candidate] = []
    for i, token in enumerate(transcript):
        entry = wordlist.lookup(normalize(token.word))
        if entry is None or not entry.context_sensitive:
            continue
        # Slurs are never un-flagged; don't waste a model call on them.
        if entry.category == "slur":
            continue
        candidates.append(
            Candidate(
                word_id=f"c{i}",
                index=i,
                token=token,
                entry=entry,
                context=build_context(transcript, i, context_window),
            )
        )
    return candidates


def disambiguate(
    candidates: list[Candidate],
    *,
    client: ModelClient,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, dict]:
    """Return {word_id: decision} for the candidates via batched model calls.

    A decision is the §7.4 object. On a model/transport error for a batch, that
    batch is dropped (callers fall back to Stage-1-only results and should note
    the degradation, per §13a).
    """
    system = _prompt()
    results: dict[str, dict] = {}

    for start in range(0, len(candidates), batch_size):
        batch = candidates[start:start + batch_size]
        items = [
            {"word_id": c.word_id, "word": c.token.word, "context": c.context}
            for c in batch
        ]
        user = (
            "Classify each candidate word IN CONTEXT. The target word in each "
            "context is wrapped in «». Respond with a JSON object of the form "
            '{"results": [ ... ]} where each element matches the contract.\n\n'
            f"CANDIDATES:\n{_dumps(items)}"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            raw = client.chat_json(messages, enable_thinking=False)
        except ModelError as exc:
            log.warning("Disambiguation batch %d dropped: %s", start // batch_size, exc)
            continue

        for decision in _coerce_results(raw):
            wid = decision.get("word_id")
            if wid:
                results[wid] = decision

    return results


# ---- helpers ----------------------------------------------------------------

def _dumps(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _coerce_results(raw) -> list[dict]:
    """Accept either a bare list or {"results": [...]} from the model."""
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        for key in ("results", "items", "data"):
            if isinstance(raw.get(key), list):
                return [x for x in raw[key] if isinstance(x, dict)]
        # Single object response.
        if "word_id" in raw:
            return [raw]
    return []
