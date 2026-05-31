"""Tests for the decision engine, profiles, coverage, and shareable export."""

from fofo_censor.audio.classify import Wordlist
from fofo_censor.decision import build_audio_edits, compute_coverage, resolve_audio_style
from fofo_censor.filtermap import FilterMap, SourceInfo, to_shareable
from fofo_censor.filtermap.schema import WordToken
from fofo_censor.profiles import default_profile, list_profiles, load_profile
from fofo_censor.profiles.schema import AudioCategory, AudioConfig, Profile


def _transcript():
    return [
        WordToken(word="this", start=0.0, end=0.3),
        WordToken(word="damn", start=0.3, end=0.6),   # profanity / mild
        WordToken(word="shit", start=0.6, end=0.9),   # profanity / moderate (stem)
        WordToken(word="thing", start=0.9, end=1.2),
    ]


def test_resolve_style_per_tier_mapping():
    profile = Profile(
        name="t",
        audio=AudioConfig(categories={
            "profanity": AudioCategory(act_on=["mild", "severe"],
                                       style={"mild": "muffle", "severe": "beep"}),
        }),
    )
    assert resolve_audio_style(profile, "profanity", "mild") == "muffle"
    assert resolve_audio_style(profile, "profanity", "severe") == "beep"
    # moderate is not in act_on -> not censored
    assert resolve_audio_style(profile, "profanity", "moderate") is None
    # unknown category -> None
    assert resolve_audio_style(profile, "slur", "severe") is None


def test_build_audio_edits_respects_act_on():
    profile = Profile(
        name="mild-only",
        audio=AudioConfig(categories={
            "profanity": AudioCategory(act_on=["mild"], style="beep"),
        }),
    )
    wl = Wordlist.load_builtin("base_profanity")
    edits = build_audio_edits(_transcript(), wl, profile, pad_sec=0.0)
    words = {e.word for e in edits}
    assert "damn" in words      # mild -> acted
    assert "shit" not in words  # moderate -> not in act_on


def test_default_profile_beeps_everything():
    wl = Wordlist.load_builtin("base_profanity")
    edits = build_audio_edits(_transcript(), wl, default_profile(), pad_sec=0.0)
    assert {e.word for e in edits} == {"damn", "shit"}
    assert all(e.style == "beep" for e in edits)


def test_coverage_counts():
    wl = Wordlist.load_builtin("base_profanity")
    fmap = FilterMap(source=SourceInfo(filename="x.mp4", duration_sec=10.0),
                     transcript=_transcript())
    fmap.audio_edits = build_audio_edits(fmap.transcript, wl, default_profile())
    cov = compute_coverage(fmap)
    assert cov.audio_edit_count == 2
    assert cov.by_category.get("profanity") == 2
    # word-level audio edits don't reduce runtime
    assert cov.filtered_runtime_pct == 0.0


def test_shareable_export_strips_audit_fields():
    wl = Wordlist.load_builtin("base_profanity")
    fmap = FilterMap(source=SourceInfo(filename="x.mp4", duration_sec=10.0),
                     transcript=_transcript())
    fmap.audio_edits = build_audio_edits(fmap.transcript, wl, default_profile())
    share = to_shareable(fmap)
    assert "transcript" not in share
    for e in share["audio_edits"]:
        assert "word" not in e
        assert "start" in e and "style" in e  # timing/decision kept


def test_starter_profile_loads_and_is_listed():
    prof = load_profile("religious-mom")
    assert prof.name == "religious-mom"
    assert "profanity" in prof.audio.categories
    assert "religious-mom" in list_profiles()
    assert "default" in list_profiles()
