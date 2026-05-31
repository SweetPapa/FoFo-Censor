"""Unit tests for wordlist matching and edit generation (no ffmpeg/whisper)."""

from fofo_censor.audio.classify import Wordlist, find_edits, normalize
from fofo_censor.filtermap.schema import WordToken


def make_wordlist():
    return Wordlist.from_dict(
        {
            "name": "test",
            "entries": [
                {"term": "damn", "category": "profanity", "tier": "mild", "match": "exact"},
                {"term": "shit", "category": "profanity", "tier": "moderate", "match": "stem"},
            ],
        }
    )


def test_normalize_strips_surrounding_punctuation():
    assert normalize("Damn!") == "damn"
    assert normalize("...shit,") == "shit"
    assert normalize("don't") == "don't"  # internal apostrophe kept


def test_exact_match_is_case_insensitive():
    wl = make_wordlist()
    assert wl.lookup("damn") is not None
    assert wl.lookup(normalize("DAMN")) is not None
    assert wl.lookup("dam") is None


def test_stem_match_catches_inflections():
    wl = make_wordlist()
    assert wl.lookup("shit") is not None
    assert wl.lookup("shitty") is not None  # stem
    assert wl.lookup("shi") is None


def test_find_edits_flags_only_matching_words_with_padding():
    wl = make_wordlist()
    transcript = [
        WordToken(word="hello", start=0.0, end=0.5),
        WordToken(word="Damn!", start=1.0, end=1.4),
        WordToken(word="world", start=1.5, end=2.0),
    ]
    edits = find_edits(transcript, wl, pad_sec=0.1)
    assert len(edits) == 1
    e = edits[0]
    assert e.word == "Damn!"
    assert e.tier == "mild"
    assert abs(e.start - 0.9) < 1e-9
    assert abs(e.end - 1.5) < 1e-9


def test_find_edits_clamps_start_at_zero():
    wl = make_wordlist()
    transcript = [WordToken(word="damn", start=0.02, end=0.3)]
    edits = find_edits(transcript, wl, pad_sec=0.1)
    assert edits[0].start == 0.0


def test_builtin_profanity_list_loads():
    wl = Wordlist.load_builtin("base_profanity")
    assert wl.lookup("damn") is not None
    assert wl.lookup("fucking") is not None  # stem
