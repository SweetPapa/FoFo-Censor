"""Stage-1 deterministic word classification (design §6.2 step 3).

A wordlist is the JSON format from §7.3. Matching normalizes each transcribed
token (lowercase, strip surrounding punctuation) and compares it to list entries.
Three match modes are supported:

  - exact : normalized token == term
  - stem  : normalized token starts with term (catches simple inflections)
  - regex : term is a full-match regex against the normalized token

Stage-2 model disambiguation for homographs/low-confidence words lives in
`audio.disambiguate` (not yet implemented).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from typing import Iterable, Optional

from ..filtermap.schema import AudioEdit, WordToken

_PUNCT_STRIP = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)


def normalize(token: str) -> str:
    return _PUNCT_STRIP.sub("", token.lower())


@dataclass
class WordlistEntry:
    term: str
    category: str
    tier: str
    match: str  # exact | stem | regex
    context_sensitive: bool = False
    _regex: Optional[re.Pattern] = None

    def matches(self, normalized_token: str) -> bool:
        if self.match == "exact":
            return normalized_token == self.term
        if self.match == "stem":
            return normalized_token.startswith(self.term)
        if self.match == "regex":
            if self._regex is None:
                self._regex = re.compile(self.term, re.IGNORECASE)
            return bool(self._regex.fullmatch(normalized_token))
        return False


class Wordlist:
    def __init__(self, name: str, entries: list[WordlistEntry]):
        self.name = name
        self.entries = entries
        self._exact = {e.term: e for e in entries if e.match == "exact"}
        self._other = [e for e in entries if e.match != "exact"]

    @classmethod
    def from_dict(cls, data: dict) -> "Wordlist":
        entries = [
            WordlistEntry(
                term=normalize(e["term"]) if e.get("match", "exact") != "regex" else e["term"],
                category=e.get("category", "profanity"),
                tier=e.get("tier", "moderate"),
                match=e.get("match", "exact"),
                context_sensitive=e.get("context_sensitive", False),
            )
            for e in data.get("entries", [])
        ]
        return cls(name=data.get("name", "unnamed"), entries=entries)

    @classmethod
    def load_file(cls, path: str) -> "Wordlist":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    @classmethod
    def load_builtin(cls, name: str = "base_profanity") -> "Wordlist":
        data = resources.files("fofo_censor.data.wordlists").joinpath(
            f"{name}.json"
        ).read_text(encoding="utf-8")
        return cls.from_dict(json.loads(data))

    @classmethod
    def merge(cls, *lists: "Wordlist") -> "Wordlist":
        """Layer multiple wordlists: later lists extend/override earlier ones (§7.3)."""
        entries: list[WordlistEntry] = []
        for wl in lists:
            entries.extend(wl.entries)
        return cls(name="merged", entries=entries)

    def lookup(self, normalized_token: str) -> Optional[WordlistEntry]:
        hit = self._exact.get(normalized_token)
        if hit:
            return hit
        for e in self._other:
            if e.matches(normalized_token):
                return e
        return None


def find_edits(
    transcript: Iterable[WordToken],
    wordlist: Wordlist,
    *,
    pad_sec: float = 0.0,
    style: str = "beep",
) -> list[AudioEdit]:
    """Match transcript words against the wordlist and produce audio edits.

    Words whose matched entry is `context_sensitive` are skipped here and would be
    routed to Stage-2 model disambiguation (`audio.disambiguate`).
    """
    edits: list[AudioEdit] = []
    for i, token in enumerate(transcript):
        entry = wordlist.lookup(normalize(token.word))
        if entry is None or entry.context_sensitive:
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
