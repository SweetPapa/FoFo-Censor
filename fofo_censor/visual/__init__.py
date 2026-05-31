"""Visual pipeline (design §6.3, M5/M6) — opt-in, the 5% path.

shots  → PySceneDetect shot boundaries + keyframe extraction
judge  → Qwen3.6 image/video classification of each shot
cutaway → one-sentence clean summary for cutaway cards

All currently stubs.
"""
