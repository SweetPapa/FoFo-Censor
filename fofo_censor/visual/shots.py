"""Shot detection + keyframe extraction (design §6.3 steps 1-2). STUB.

Uses PySceneDetect for shot boundaries, then extracts a representative keyframe
per shot (scene-change aligned) for the visual judge.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Shot:
    shot_id: str
    start: float
    end: float
    keyframe_path: str | None = None


def detect_shots(input_path: str) -> list[Shot]:
    raise NotImplementedError("Shot detection (M5) is not implemented (needs PySceneDetect).")


def extract_keyframe(input_path: str, shot: Shot, out_dir: str) -> str:
    raise NotImplementedError("Keyframe extraction (M5) is not implemented.")
