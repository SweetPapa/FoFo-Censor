"""Audio-edit filtering with ffmpeg (design §6.7).

Supported styles in this MVP, all applied with a single expression-driven filter
chain over the flagged word windows:

  - silence : mute the window
  - beep    : mute the window and overlay a 1 kHz tone
  - muffle  : low-pass the window (audio stays, intelligibility drops)

`reverse` and `safe_replace` are defined in the schema but not implemented yet;
they are downgraded to `beep` with a logged warning so a profile that requests
them still renders.

`audio_filter()` builds the filter-graph fragment and is reused by both the
fast audio-only render here and the full re-encode path in `pipeline.py`. The
plain `render()` below stream-copies the video (no disclaimer card).
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional, Sequence

from ..filtermap.schema import AudioEdit
from ..probe import probe, require_tool

log = logging.getLogger("fofo_censor.render")

BEEP_FREQ_HZ = 1000
WORK_RATE = 44100
MUFFLE_CUTOFF_HZ = 400

# Styles that mute the original audio in their window.
_MUTING = {"silence", "beep", "reverse", "safe_replace"}
# Styles that get a beep tone overlaid (downgrades included).
_BEEPING = {"beep", "reverse", "safe_replace"}
_DOWNGRADED = {"reverse", "safe_replace"}


def default_output_path(input_path: str) -> str:
    base, ext = os.path.splitext(input_path)
    return f"{base}.censored{ext or '.mp4'}"


def _between_sum(edits: Sequence[AudioEdit]) -> str:
    if not edits:
        return "0"
    return "+".join(f"between(t,{e.start:.3f},{e.end:.3f})" for e in edits)


@dataclass
class AudioFilter:
    """A built audio filter graph fragment.

    `parts` are filtergraph statements to join with ';'. `out_label` is the
    labelled output pad (e.g. "aout"). `needs_beep_input` signals the caller to
    add the sine `lavfi` input *as the input immediately after the main input*
    (so its stream specifier is `[1:a]`, which the parts reference).
    """

    parts: list[str]
    out_label: str
    needs_beep_input: bool


def warn_downgrades(edits: Sequence[AudioEdit]) -> None:
    downgraded = [e for e in edits if e.style in _DOWNGRADED]
    if downgraded:
        styles = sorted({e.style for e in downgraded})
        log.warning("Styles %s not implemented yet; rendering as 'beep'.", styles)


def audio_filter(
    edits: Sequence[AudioEdit],
    *,
    audio_track_index: int = 0,
    beep_input_label: str = "1:a",
) -> AudioFilter:
    """Build the censoring audio filter graph for the given edits.

    The beep tone, when needed, is expected at `beep_input_label`. The output is
    resampled to WORK_RATE; callers that concat with other audio should append an
    `aformat` to normalize channel layout.
    """
    mute_edits = [e for e in edits if e.style in _MUTING]
    beep_edits = [e for e in edits if e.style in _BEEPING]
    muffle_edits = [e for e in edits if e.style == "muffle"]

    mute_expr = f"gt({_between_sum(mute_edits)},0)"
    muffle_expr = f"gt({_between_sum(muffle_edits)},0)"
    beep_expr = f"gt({_between_sum(beep_edits)},0)"

    chain = [f"[0:a:{audio_track_index}]aresample={WORK_RATE}",
             f"volume='1-{mute_expr}':eval=frame"]
    if muffle_edits:
        chain.append(f"lowpass=f={MUFFLE_CUTOFF_HZ}:enable='{muffle_expr}'")
    parts = [",".join(chain) + "[a0]"]

    if beep_edits:
        parts.append(f"[{beep_input_label}]volume='{beep_expr}':eval=frame[beep]")
        # duration=first bounds the mix to the (finite) program audio; the sine
        # tone source is infinite, so without this the output never ends — which
        # also breaks the downstream concat in pipeline.render.
        parts.append("[a0][beep]amix=inputs=2:normalize=0:duration=first[aout]")
        out_label = "aout"
        needs_beep = True
    else:
        out_label = "a0"
        needs_beep = False

    return AudioFilter(parts=parts, out_label=out_label, needs_beep_input=needs_beep)


def beep_input_args() -> list[str]:
    """ffmpeg input args for the 1 kHz tone source."""
    return ["-f", "lavfi", "-i",
            f"sine=frequency={BEEP_FREQ_HZ}:sample_rate={WORK_RATE}"]


def render(
    input_path: str,
    edits: Sequence[AudioEdit],
    output_path: Optional[str] = None,
    *,
    audio_track_index: int = 0,
    quiet: bool = True,
) -> str:
    """Audio-only censor render with the video stream copied. No disclaimer card.

    Use `pipeline.render` for the standard path (which prepends the mandatory
    disclaimer card and re-encodes per §10a).
    """
    ffmpeg = require_tool("ffmpeg")
    out = output_path or default_output_path(input_path)
    info = probe(input_path)

    if not edits:
        _run([ffmpeg, "-y", "-i", input_path, "-c", "copy", out], quiet)
        return out

    warn_downgrades(edits)
    af = audio_filter(edits, audio_track_index=audio_track_index)

    cmd = [ffmpeg, "-y", "-i", input_path]
    if af.needs_beep_input:
        cmd += beep_input_args()
    cmd += ["-filter_complex", ";".join(af.parts)]
    if info.has_video:
        cmd += ["-map", "0:v", "-c:v", "copy"]
    cmd += ["-map", f"[{af.out_label}]", "-c:a", "aac", "-b:a", "192k", "-shortest", out]

    _run(cmd, quiet)
    return out


def _run(cmd: list[str], quiet: bool) -> None:
    if quiet:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    else:
        subprocess.run(cmd, check=True)
