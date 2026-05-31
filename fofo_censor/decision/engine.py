"""Decision engine (design §6.4, §8).

Turns Stage-1 wordlist hits into audio edits with the style resolved from the
active profile (per category, optionally per tier). Stage-2 model disambiguation
of context-sensitive homographs is merged in via `build_disambiguated_edits`.
Visual decisions (§8 rules 3-4) belong here too and are stubbed until the visual
pipeline lands.
"""

from __future__ import annotations

from typing import Optional

from ..audio.classify import Wordlist, normalize
from ..filtermap.schema import AudioEdit, WordToken
from ..profiles.schema import Profile

_VALID_CATEGORIES = ("profanity", "slur", "sexual_term")
_VALID_TIERS = ("mild", "moderate", "severe")


def _valid(value, allowed, fallback):
    return value if value in allowed else fallback


def resolve_audio_style(profile: Profile, category: str, tier: str) -> Optional[str]:
    """Return the censor style for a (category, tier), or None if not acted on.

    `act_on` may be a list of tiers or ["all"]. `style` may be a single string or
    a per-tier mapping.
    """
    cat = profile.audio.categories.get(category)
    if cat is None:
        return None

    act_on = cat.act_on
    if "all" not in act_on and tier not in act_on:
        return None

    style = cat.style
    if isinstance(style, dict):
        return style.get(tier) or next(iter(style.values()), None)
    return style


def build_audio_edits(
    transcript: list[WordToken],
    wordlist: Wordlist,
    profile: Profile,
    *,
    pad_sec: float = 0.05,
) -> list[AudioEdit]:
    """Profile-aware audio edit construction (design §6.2 step 5)."""
    edits: list[AudioEdit] = []
    for i, token in enumerate(transcript):
        entry = wordlist.lookup(normalize(token.word))
        if entry is None or entry.context_sensitive:
            continue
        style = resolve_audio_style(profile, entry.category, entry.tier)
        if style is None:
            continue
        edits.append(
            AudioEdit(
                id=f"a{i}",
                start=max(0.0, token.start - pad_sec),
                end=token.end + pad_sec,
                word=token.word,
                category=entry.category,
                tier=entry.tier,
                style=style,
                source="list",
            )
        )
    return edits


def build_disambiguated_edits(
    transcript: list[WordToken],
    wordlist: Wordlist,
    profile: Profile,
    *,
    client,
    pad_sec: float = 0.05,
) -> list[AudioEdit]:
    """Stage-2: resolve context-sensitive homographs via the model (design §6.2 step 4).

    Words the model judges not objectionable are left uncensored. Confirmed hits
    get a profile-resolved style; if the profile doesn't act on that
    category/tier, the hit is dropped. Edits are marked `source="model"`.

    Imported lazily so the audio MVP and tests don't require the model layer.
    """
    from ..audio.disambiguate import collect_candidates, disambiguate

    candidates = collect_candidates(transcript, wordlist)
    if not candidates:
        return []

    decisions = disambiguate(candidates, client=client)

    edits: list[AudioEdit] = []
    for c in candidates:
        d = decisions.get(c.word_id)
        if d is None or not d.get("is_objectionable"):
            # No decision (dropped batch) or judged benign -> don't censor.
            continue
        category = _valid(d.get("category"), _VALID_CATEGORIES, c.entry.category)
        tier = _valid(d.get("tier"), _VALID_TIERS, c.entry.tier)
        style = resolve_audio_style(profile, category, tier)
        if style is None:
            continue
        edits.append(
            AudioEdit(
                id=f"d{c.index}",
                start=max(0.0, c.token.start - pad_sec),
                end=c.token.end + pad_sec,
                word=c.token.word,
                category=category,
                tier=tier,
                style=style,
                source="model",
                model_confidence=_as_float(d.get("confidence")),
            )
        )
    return edits


def build_scanned_edits(
    transcript: list[WordToken],
    profile: Profile,
    *,
    client,
    pad_sec: float = 0.05,
    exclude_indices: Optional[set[int]] = None,
) -> list[AudioEdit]:
    """Holistic pass: flag objectionable words anywhere, even if unlisted (§6.2).

    Sends the whole transcript to the model (see `audio.scan`) and turns each
    verified hit into a profile-styled edit. `exclude_indices` lets callers skip
    tokens already covered by Stage-1/Stage-2 so the same word isn't double-edited.
    Edits are marked `source="model"`.

    Imported lazily so the audio MVP and tests don't require the model layer.
    """
    from ..audio.scan import scan_transcript

    exclude = exclude_indices or set()
    hits = scan_transcript(transcript, client=client)

    edits: list[AudioEdit] = []
    for hit in hits:
        if hit.index in exclude:
            continue
        token = transcript[hit.index]
        style = resolve_audio_style(profile, hit.category, hit.tier)
        if style is None:
            continue
        edits.append(
            AudioEdit(
                id=f"s{hit.index}",
                start=max(0.0, token.start - pad_sec),
                end=token.end + pad_sec,
                word=token.word,
                category=hit.category,
                tier=hit.tier,
                style=style,
                source="model",
            )
        )
    return edits


def _as_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
