"""Top-level render orchestration (design §6.7, §10a, §12).

`render()` is the standard entry point. When a disclaimer card is requested
(the default for video output), it prepends the mandatory black-slate card and
re-encodes in a single ffmpeg pass — a generated card can't be stream-copied in,
so §10a's full re-encode applies. With no card it delegates to the fast
audio-only path that stream-copies the video.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Sequence

from ..filtermap.schema import AudioEdit
from ..probe import probe, require_tool
from . import beep
from . import disclaimer as disc
from .encode import RenderSettings, audio_encoder_args, video_encoder_args

log = logging.getLogger("fofo_censor.render")

WORK_RATE = beep.WORK_RATE


def render(
    input_path: str,
    edits: Sequence[AudioEdit],
    output_path: Optional[str] = None,
    *,
    audio_track_index: int = 0,
    disclaimer_text: Optional[str] = None,
    dwell_sec: Optional[float] = None,
    render_settings: Optional[RenderSettings] = None,
    quiet: bool = True,
) -> str:
    """Render a censored copy, optionally prepending the disclaimer card.

    If `disclaimer_text` is None, uses the fast stream-copy audio render.
    """
    out = output_path or beep.default_output_path(input_path)
    info = probe(input_path)

    # No card (or no video to put one on) -> fast audio-only path.
    if disclaimer_text is None or not info.has_video:
        if disclaimer_text is not None and not info.has_video:
            log.warning("Input has no video stream; skipping disclaimer card.")
        return beep.render(input_path, edits, out,
                           audio_track_index=audio_track_index, quiet=quiet)

    ffmpeg = require_tool("ffmpeg")
    settings = render_settings or RenderSettings()
    beep.warn_downgrades(edits)

    fps = info.fps or 25.0
    width, height = info.width, info.height
    dwell = dwell_sec or disc.compute_dwell(disclaimer_text)

    # Write the wrapped card text to a temp file for drawtext.
    tmpdir = tempfile.mkdtemp(prefix="fofo_card_")
    textfile = disc.write_wrapped_textfile(
        disclaimer_text, width, disc._font_size(height), Path(tmpdir) / "card.txt"
    )

    try:
        af = beep.audio_filter(edits, audio_track_index=audio_track_index)
        card = disc.build_card_filter(
            disclaimer_text, width=width, height=height, fps=fps,
            dwell_sec=dwell, textfile_path=str(textfile), sample_rate=WORK_RATE,
        )

        # Normalize feature streams so concat sees identical params on both
        # segments (card and feature).
        feature_audio = (
            f"[{af.out_label}]aformat=channel_layouts=stereo:sample_rates={WORK_RATE}[fa]"
        )
        feature_video = (
            f"[0:v]fps={max(1, int(round(fps)))},scale={width}:{height}:flags=bicubic,"
            f"setsar=1,format=yuv420p[fv]"
        )
        concat = (
            f"[{card.video_label}][{card.audio_label}][fv][fa]"
            f"concat=n=2:v=1:a=1[outv][outa]"
        )

        parts = af.parts + card.parts + [feature_audio, feature_video, concat]

        cmd = [ffmpeg, "-y", "-i", input_path]
        if af.needs_beep_input:
            cmd += beep.beep_input_args()
        cmd += ["-filter_complex", ";".join(parts)]
        cmd += ["-map", "[outv]", "-map", "[outa]"]
        cmd += video_encoder_args(settings.video_codec, settings.encoder, settings.quality)
        cmd += audio_encoder_args(settings)
        cmd += [out]

        _run(cmd, quiet)
        return out
    finally:
        try:
            os.remove(textfile)
            os.rmdir(tmpdir)
        except OSError:
            pass


def _run(cmd: list[str], quiet: bool) -> None:
    if quiet:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    else:
        subprocess.run(cmd, check=True)
