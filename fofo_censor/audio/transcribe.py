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


def transcribe_words(
    input_path: str,
    *,
    model_size: str = "base.en",
    device: str = "cpu",
    compute_type: str = "int8",
    language: Optional[str] = None,
    audio_track_index: int = 0,
    on_progress=None,
) -> list[WordToken]:
    """Transcribe a media file to a flat list of timestamped words.

    `on_progress(segment_text, end_time)` is called per segment if provided, so a
    CLI can show live progress.
    """
    # Imported lazily so `--help` and non-transcribe commands don't pay the
    # heavy import / model-load cost.
    from faster_whisper import WhisperModel

    wav_path = extract_audio_wav(input_path, audio_track_index)
    try:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments, _info = model.transcribe(
            wav_path,
            language=language,
            word_timestamps=True,
            vad_filter=True,
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
