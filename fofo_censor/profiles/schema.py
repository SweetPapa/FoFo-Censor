"""Profile schema (design §7.2).

The audio section is fully modeled because the decision engine relies on it. The
safe_replace / visual / cutaway / tts / disclaimer / render sections are modeled
loosely (extra fields allowed) since their consumers are still stubs — this keeps
real profile files valid today without over-committing the schema.
"""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict, Field


class AudioCategory(BaseModel):
    # act_on: list of tiers, or ["all"]
    act_on: list[str] = Field(default_factory=lambda: ["all"])
    # style: a single style, or a per-tier mapping {tier: style}
    style: Union[str, dict[str, str]] = "beep"


class AudioConfig(BaseModel):
    categories: dict[str, AudioCategory] = Field(default_factory=dict)
    wordlists: list[str] = Field(default_factory=lambda: ["base_profanity"])
    preserve_context_segments: bool = True


class Profile(BaseModel):
    model_config = ConfigDict(extra="allow")  # tolerate not-yet-modeled sections

    name: str
    description: str = ""
    audio: AudioConfig = Field(default_factory=AudioConfig)
    # safe_replace / visual / cutaway / tts / disclaimer / render are accepted as
    # extra fields until their pipelines are implemented.
