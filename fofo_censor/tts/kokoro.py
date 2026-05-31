"""Kokoro TTS wrapper with a clip cache (design §6.5). STUB.

Synthesizes cutaway narration and safe-word replacement clips. Clips are cached
keyed by (text, voice) so re-renders are free. Window fitting lives in
`audio.safeword.fit_clip_to_window`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from ..config import app_paths


class KokoroTTS:
    def __init__(self, voice: str = "default", rate: float = 1.0,
                 cache_dir: Optional[Path] = None):
        self.voice = voice
        self.rate = rate
        self.cache_dir = cache_dir or app_paths().tts_cache_dir

    def _cache_key(self, text: str) -> Path:
        digest = hashlib.sha256(f"{self.voice}:{self.rate}:{text}".encode()).hexdigest()[:16]
        return self.cache_dir / f"{digest}.wav"

    def synthesize(self, text: str) -> str:
        """Return a path to a synthesized WAV (cached). Not implemented yet."""
        raise NotImplementedError(
            "Kokoro synthesis (M3) is not implemented. Cache clips at "
            "self._cache_key(text)."
        )
