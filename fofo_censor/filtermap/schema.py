"""Pydantic models for the FoFo-Censor filter map sidecar (design §7.1).

The audio MVP only populates `source`, `transcript`, and `audio_edits`. The
remaining sections (visual edits, coverage, profile/model snapshots) are modeled
here with defaults so the schema is complete and forward-compatible — older
sidecars still load, and new pipeline stages can fill these in without a
migration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.2"


class SourceInfo(BaseModel):
    filename: str
    duration_sec: float
    resolution: Optional[str] = None
    fps: Optional[float] = None
    fingerprint: Optional[str] = None
    audio_track_index: int = 0


class ModelSnapshot(BaseModel):
    transcription: str = "faster-whisper"
    vision_text: Optional[str] = None
    tts: Optional[str] = None
    endpoint: Optional[str] = None
    prompt_version: Optional[str] = None


class WordToken(BaseModel):
    """One transcribed word with its timing, from Whisper."""

    word: str
    start: float
    end: float
    probability: Optional[float] = None


class AudioEdit(BaseModel):
    """A region of audio to censor."""

    id: str
    start: float
    end: float
    word: str  # local-only audit field; stripped in shareable export
    category: Literal["profanity", "slur", "sexual_term"] = "profanity"
    tier: Literal["mild", "moderate", "severe"] = "moderate"
    style: Literal["beep", "silence", "reverse", "muffle", "safe_replace"] = "beep"
    replacement_text: Optional[str] = None  # when style == safe_replace
    tts_clip: Optional[str] = None
    source: Literal["list", "model"] = "list"
    model_confidence: Optional[float] = None


class VisualDetection(BaseModel):
    violence_level: Literal["none", "stylized", "realistic", "implied"] = "none"
    sexual_level: Literal["none", "suggestive", "explicit"] = "none"
    confidence: float = 0.0
    tier_used: Literal["image", "video"] = "image"
    description: str = ""  # local-only; stripped in shareable export


class VisualEdit(BaseModel):
    id: str
    shot_id: str
    start: float
    end: float
    detected: VisualDetection = Field(default_factory=VisualDetection)
    action: Literal["cutaway", "blackbar", "blur", "none"] = "none"
    summary_text: Optional[str] = None
    tts_clip: Optional[str] = None
    user_confirmed: bool = False
    user_overridden: bool = False


class Coverage(BaseModel):
    total_edits: int = 0
    audio_edit_count: int = 0
    visual_edit_count: int = 0
    filtered_runtime_sec: float = 0.0
    filtered_runtime_pct: float = 0.0
    by_category: dict[str, int] = Field(default_factory=dict)


class ProfileRef(BaseModel):
    name: str = "default"
    snapshot: dict = Field(default_factory=dict)


class FilterMap(BaseModel):
    fofocensor_version: str = SCHEMA_VERSION
    created_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: SourceInfo
    profile: ProfileRef = Field(default_factory=ProfileRef)
    models: ModelSnapshot = Field(default_factory=ModelSnapshot)
    transcript: list[WordToken] = Field(default_factory=list)
    audio_edits: list[AudioEdit] = Field(default_factory=list)
    visual_edits: list[VisualEdit] = Field(default_factory=list)
    coverage: Coverage = Field(default_factory=Coverage)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: str) -> "FilterMap":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.model_validate_json(fh.read())
