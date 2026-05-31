"""Visual judgment via Qwen3.6 (design §6.3 steps 3-4, §7.4). STUB.

Tier-1: keyframe(s) as image_url → {violence_level, sexual_level, confidence,
description}. Tier-2 (only when confidence is low): a short clip as video_url for
a motion-aware second opinion. Stylized/cartoon violence is NOT flagged; only
realistic harm or actual nudity/explicit content.
"""

from __future__ import annotations

from typing import Optional

from ..filtermap.schema import VisualDetection
from ..model import ModelClient
from .shots import Shot


def judge_shot_image(shot: Shot, *, client: Optional[ModelClient] = None) -> VisualDetection:
    raise NotImplementedError("Tier-1 image judgment (M5) is not implemented.")


def judge_shot_video(
    input_path: str, shot: Shot, *, fps: float = 1.0, client: Optional[ModelClient] = None
) -> VisualDetection:
    raise NotImplementedError("Tier-2 video judgment (M6) is not implemented.")
