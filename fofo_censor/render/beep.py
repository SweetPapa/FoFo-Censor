"""Audio-edit rendering with ffmpeg (design §6.7).

Supported styles in this MVP, all applied in a single ffmpeg pass over the
flagged word windows:

  - silence : mute the window
  - beep    : mute the window and overlay a 1 kHz tone
  - muffle  : low-pass the window (audio stays, intelligibility drops)

`reverse` and `safe_replace` are defined in the schema but not implemented yet;
they are downgraded to `beep` with a logged warning so a profile that requests
them still renders. The video stream is copied (no re-encode).
"""

from __future__ import annotations

import logging
import os
import subprocess
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


def render(
    input_path: str,
    edits: Sequence[AudioEdit],
    output_path: Optional[str] = None,
    *,
    audio_track_index: int = 0,
    quiet: bool = True,
) -> str:
    """Produce a censored copy. Returns the output path."""
    ffmpeg = require_tool("ffmpeg")
    out = output_path or default_output_path(input_path)
    info = probe(input_path)

    if not edits:
        _run([ffmpeg, "-y", "-i", input_path, "-c", "copy", out], quiet)
        return out

    downgraded = [e for e in edits if e.style in _DOWNGRADED]
    if downgraded:
        styles = sorted({e.style for e in downgraded})
        log.warning("Styles %s not implemented yet; rendering as 'beep'.", styles)

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
    filter_parts = [",".join(chain) + "[a0]"]

    cmd = [ffmpeg, "-y", "-i", input_path]
    if beep_edits:
        cmd += ["-f", "lavfi", "-i",
                f"sine=frequency={BEEP_FREQ_HZ}:sample_rate={WORK_RATE}"]
        filter_parts.append(f"[1:a]volume='{beep_expr}':eval=frame[beep]")
        filter_parts.append("[a0][beep]amix=inputs=2:normalize=0[aout]")
        audio_out = "[aout]"
    else:
        audio_out = "[a0]"

    cmd += ["-filter_complex", ";".join(filter_parts)]
    if info.has_video:
        cmd += ["-map", "0:v", "-c:v", "copy"]
    cmd += ["-map", audio_out, "-c:a", "aac", "-b:a", "192k", "-shortest", out]

    _run(cmd, quiet)
    return out


def _run(cmd: list[str], quiet: bool) -> None:
    if quiet:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    else:
        subprocess.run(cmd, check=True)
