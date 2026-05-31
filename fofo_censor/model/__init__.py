"""OpenAI-compatible model client (design §4, §7.4).

Wraps the local inference endpoint used for visual judgment, audio
disambiguation, cutaway summaries, and safe-word generation. All higher-level
features (audio.disambiguate, audio.safeword, visual.judge, visual.cutaway) call
through here so batching, retries, and the endpoint URL live in one place.
"""

from .client import ModelClient, ModelConfig

__all__ = ["ModelClient", "ModelConfig"]
