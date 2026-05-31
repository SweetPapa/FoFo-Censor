"""Coverage statistics and the "Boondocks guard" warning (design §10)."""

from __future__ import annotations

from ..filtermap.schema import Coverage, FilterMap


def compute_coverage(fmap: FilterMap) -> Coverage:
    """Compute coverage stats from the edits in a filter map.

    Note: pure word-level audio edits don't reduce runtime, so
    `filtered_runtime_*` is driven by visual cutaways/skips (§10). A high audio
    edit *count* drives the softer "heavily censored" notice instead.
    """
    by_category: dict[str, int] = {}
    for e in fmap.audio_edits:
        by_category[e.category] = by_category.get(e.category, 0) + 1

    visual_runtime = 0.0
    for v in fmap.visual_edits:
        if v.action in ("cutaway",):
            visual_runtime += max(0.0, v.end - v.start)
        key = "realistic_violence" if v.detected.violence_level == "realistic" else None
        if v.detected.sexual_level == "explicit":
            key = "explicit_sexual"
        if key:
            by_category[key] = by_category.get(key, 0) + 1

    duration = fmap.source.duration_sec or 0.0
    pct = (visual_runtime / duration * 100.0) if duration else 0.0

    return Coverage(
        total_edits=len(fmap.audio_edits) + len(fmap.visual_edits),
        audio_edit_count=len(fmap.audio_edits),
        visual_edit_count=len(fmap.visual_edits),
        filtered_runtime_sec=round(visual_runtime, 3),
        filtered_runtime_pct=round(pct, 2),
        by_category=by_category,
    )


def coverage_warning(coverage: Coverage, *, threshold_pct: float = 40.0) -> str | None:
    """Return a hard warning if too much runtime is cut, else None (§10)."""
    if coverage.filtered_runtime_pct >= threshold_pct:
        return (
            f"This profile would modify ~{coverage.filtered_runtime_pct:.0f}% of "
            "this title's runtime. The result may be choppy or lose meaning."
        )
    return None
