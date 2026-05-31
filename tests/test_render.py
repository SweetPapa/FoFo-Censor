"""Tests for the render layer: audio filter, disclaimer card, encode settings.

The filter-construction tests need no ffmpeg. The end-to-end render test is
skipped automatically when ffmpeg is not installed.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from fofo_censor.filtermap.schema import AudioEdit
from fofo_censor.render import beep, disclaimer as disc
from fofo_censor.render.encode import RenderSettings, video_encoder_args

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _edit(start, end, style="beep"):
    return AudioEdit(id="x", start=start, end=end, word="w", style=style)


# ---- audio filter -----------------------------------------------------------

def test_audio_filter_beep_needs_tone_input():
    af = beep.audio_filter([_edit(1.0, 1.5, "beep")])
    assert af.needs_beep_input is True
    assert af.out_label == "aout"
    joined = ";".join(af.parts)
    assert "between(t,1.000,1.500)" in joined
    assert "amix" in joined


def test_audio_filter_silence_no_tone_input():
    af = beep.audio_filter([_edit(2.0, 2.4, "silence")])
    assert af.needs_beep_input is False
    assert af.out_label == "a0"
    assert "amix" not in ";".join(af.parts)


def test_audio_filter_muffle_adds_lowpass():
    af = beep.audio_filter([_edit(0.0, 1.0, "muffle")])
    assert "lowpass" in ";".join(af.parts)


# ---- disclaimer card --------------------------------------------------------

def test_compute_dwell_clamps():
    assert disc.compute_dwell("one two three", min_sec=2.5, max_sec=12.0) == 2.5
    long_text = " ".join(["word"] * 1000)
    assert disc.compute_dwell(long_text, min_sec=2.5, max_sec=8.0) == 8.0


def test_write_wrapped_textfile(tmp_path):
    dest = tmp_path / "card.txt"
    text = "This is a fairly long paragraph that should wrap across lines.\n\nSecond paragraph."
    disc.write_wrapped_textfile(text, width=320, font_size=16, dest=dest)
    content = dest.read_text(encoding="utf-8")
    assert "\n" in content
    assert "fairly long paragraph" in content


def test_build_card_filter_structure(tmp_path):
    tf = tmp_path / "c.txt"
    tf.write_text("hello", encoding="utf-8")
    card = disc.build_card_filter(
        "hello", width=640, height=480, fps=30.0, dwell_sec=3.0,
        textfile_path=str(tf),
    )
    joined = ";".join(card.parts)
    assert "color=c=black:s=640x480" in joined
    assert "drawtext=" in joined
    assert f"[{card.video_label}]" in joined
    assert f"[{card.audio_label}]" in joined
    assert card.dwell_sec == 3.0


def test_default_disclaimer_text_mentions_family_movie_act():
    text = disc.default_disclaimer_text()
    assert "Family Movie Act" in text


# ---- encode settings --------------------------------------------------------

def test_render_settings_from_profile_block():
    s = RenderSettings.from_profile_block(
        {"video_codec": "hevc", "encoder": "software", "quality": 22}
    )
    assert s.video_codec == "hevc"
    assert s.quality == 22


def test_video_encoder_args_mapping():
    assert video_encoder_args("h264", "software", 20) == ["-c:v", "libx264", "-crf", "20"]
    assert video_encoder_args("hevc", "nvenc", 24) == ["-c:v", "hevc_nvenc", "-cq", "24"]
    with pytest.raises(ValueError):
        video_encoder_args("bogus", "software", 20)


# ---- end-to-end render (needs ffmpeg) ---------------------------------------

def _ffprobe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_render_prepends_disclaimer_card(tmp_path):
    from fofo_censor.render import render

    src = tmp_path / "src.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=navy:s=320x240:d=2",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:d=2",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         str(src)],
        capture_output=True, text=True, check=True,
    )
    base = _ffprobe_duration(str(src))

    out = tmp_path / "out.mp4"
    render(str(src), [_edit(0.5, 1.0, "beep")], str(out),
           disclaimer_text="This is a filtered version for private home viewing.",
           dwell_sec=3.0, render_settings=RenderSettings())

    assert out.exists()
    result = _ffprobe_duration(str(out))
    # Output should be roughly the source plus the 3s card.
    assert result >= base + 2.5
