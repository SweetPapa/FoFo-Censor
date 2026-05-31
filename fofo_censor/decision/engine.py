"""Decision engine (design §6.4, §8).

Turns Stage-1 wordlist hits into audio edits with the style resolved from the
active profile (per category, optionally per tier). Visual decisions (§8 rules
3-4) belong here too and are stubbed until the visual pipeline lands.
"""

from __future__ import annotations

from typing import Optional

from ..audio.classify import Wordlist, normalize
from ..filtermap.schema import AudioEdit, WordToken
from ..profiles.schema import Profile


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
