"""Whisper transcription with word-level timestamps (via faster-whisper).

Runs locally on CPU by default (int8) so it works on any machine; pass a
different device/compute type for GPU. Audio is first extracted to a mono 16 kHz
WAV with ffmpeg, which is what Whisper wants and keeps decoding robust across
container formats.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Optional

from ..filtermap.schema import WordToken
from ..probe import require_tool

# Whisper is trained to produce "clean" text and will euphemize or drop profanity,
# especially smaller models. Seeding the decoder with a profanity-laden prompt
# biases it to transcribe such words verbatim — which is exactly what a censor
# tool needs, since a word that's never transcribed can never be flagged. This is
# the standard anti-sanitization trick. Pass initial_prompt=None to disable.
PROFANITY_HINT = (
    "Okay, here's the deal. Damn it, this shit is fucked up. "
    "He's a real asshole, a goddamn bastard. Bitch, please. What the hell."
)


def extract_audio_wav(input_path: str, audio_track_index: int = 0) -> str:
    """Extract one audio track to a temp 16 kHz mono WAV. Caller deletes it."""
    ffmpeg = require_tool("ffmpeg")
    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="fofo_")
    os.close(fd)
    cmd = [
        ffmpeg, "-y",
        "-i", input_path,
        "-map", f"0:a:{audio_track_index}",
        "-ac", "1",
        "-ar", "16000",
        "-vn",
        wav_path,
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return wav_path


_UNSET = object()


def transcribe_words(
    input_path: str,
    *,
    model_size: str = "medium.en",
    device: str = "cpu",
    compute_type: str = "int8",
    language: Optional[str] = None,
    audio_track_index: int = 0,
    vad_filter: bool = True,
    beam_size: int = 5,
    initial_prompt=_UNSET,
    on_progress=None,
) -> list[WordToken]:
    """Transcribe a media file to a flat list of timestamped words.

    `on_progress(segment_text, end_time)` is called per segment if provided, so a
    CLI can show live progress.

    Defaults to the `medium.en` model: profanity detection lives or dies on
    transcription accuracy, and `medium` misses noticeably fewer words than
    `small` on fast or overlapping speech. Use `small.en` for speed or `large-v3`
    for maximum accuracy.

    `initial_prompt` defaults to `PROFANITY_HINT`, which stops Whisper from
    sanitizing swear words; pass `None` to disable or a string to override. VAD is
    on by default with a conservative `min_silence_duration_ms` so it trims
    silence without clipping short words; pass `vad_filter=False` to disable it.
    """
    # Imported lazily so `--help` and non-transcribe commands don't pay the
    # heavy import / model-load cost.
    from faster_whisper import WhisperModel

    prompt = PROFANITY_HINT if initial_prompt is _UNSET else initial_prompt

    wav_path = extract_audio_wav(input_path, audio_track_index)
    try:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments, _info = model.transcribe(
            wav_path,
            language=language,
            word_timestamps=True,
            beam_size=beam_size,
            initial_prompt=prompt,
            vad_filter=vad_filter,
            # Less aggressive than the default 2000ms so brief words between
            # short pauses aren't dropped (addresses missed-word reports).
            vad_parameters={"min_silence_duration_ms": 500} if vad_filter else None,
        )

        words: list[WordToken] = []
        for seg in segments:
            if on_progress is not None:
                on_progress(seg.text.strip(), seg.end)
            for w in (seg.words or []):
                token = WordToken(
                    word=w.word.strip(),
                    start=float(w.start),
                    end=float(w.end),
                    probability=float(w.probability) if w.probability is not None else None,
                )
                if token.word:
                    words.append(token)
        return words
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass
