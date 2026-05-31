"""Tests for the holistic full-transcript scan (no network; fake client)."""

from fofo_censor.audio.scan import scan_transcript, _coerce_flagged
from fofo_censor.decision import build_scanned_edits
from fofo_censor.filtermap.schema import WordToken
from fofo_censor.profiles import default_profile


def _transcript(words):
    return [WordToken(word=w, start=i * 0.5, end=i * 0.5 + 0.3)
            for i, w in enumerate(words)]


def _parse_words(user_content):
    """Extract the WORDS:[...] array the scan prompt sends to the model."""
    import json
    body = user_content[user_content.index("WORDS:") + len("WORDS:"):]
    return json.loads(body[body.index("["):body.rfind("]") + 1])


class ScanFake:
    """Flags any token whose normalized word is in `bad`, returning correct indices."""

    def __init__(self, bad, *, lie_index=False, drop_word=False):
        self.bad = {w.lower() for w in bad}
        self.lie_index = lie_index
        self.drop_word = drop_word
        self.calls = 0

    def healthcheck(self):
        return True

    def chat_json(self, messages, *, enable_thinking=None, max_tokens=2048):
        self.calls += 1
        items = _parse_words(messages[-1]["content"])
        flagged = []
        for it in items:
            if it["word"].lower().strip(".,!?") in self.bad:
                entry = {"index": it["index"], "word": it["word"],
                         "category": "profanity", "tier": "moderate"}
                if self.lie_index:
                    entry["index"] = 99999  # force word-based recovery
                if self.drop_word:
                    entry.pop("word")
                flagged.append(entry)
        return {"flagged": flagged}


# ---- scan_transcript --------------------------------------------------------

def test_scan_finds_unlisted_words_with_correct_indices():
    t = _transcript(["this", "is", "frigging", "great", "you", "twit"])
    client = ScanFake({"frigging", "twit"})
    hits = scan_transcript(t, client=client)
    assert [(h.index, h.word) for h in hits] == [(2, "frigging"), (5, "twit")]


def test_scan_recovers_when_index_is_wrong():
    """A hallucinated index is corrected by matching the word within the chunk."""
    t = _transcript(["hello", "you", "git", "there"])
    client = ScanFake({"git"}, lie_index=True)
    hits = scan_transcript(t, client=client)
    assert len(hits) == 1
    assert hits[0].index == 2 and hits[0].word == "git"


def test_scan_drops_unlocalizable_hit():
    """If the model returns a bad index and no usable word, the hit is dropped."""
    t = _transcript(["all", "clean", "here"])

    class Bogus(ScanFake):
        def chat_json(self, messages, *, enable_thinking=None, max_tokens=2048):
            return {"flagged": [{"index": 100, "category": "profanity", "tier": "mild"}]}

    hits = scan_transcript(t, client=Bogus(set()))
    assert hits == []


def test_scan_dedupes_across_overlapping_chunks():
    # Force tiny chunks with overlap so a word can appear in two windows.
    words = [f"w{i}" for i in range(10)]
    words[5] = "crap"
    t = _transcript(words)
    client = ScanFake({"crap"})
    hits = scan_transcript(t, client=client, chunk_size=6, overlap=3)
    assert [h.index for h in hits] == [5]  # de-duped to a single hit
    assert client.calls >= 2  # actually chunked


def test_scan_empty_transcript():
    assert scan_transcript([], client=ScanFake(set())) == []


# ---- build_scanned_edits ----------------------------------------------------

def test_build_scanned_edits_applies_profile_style_and_excludes():
    t = _transcript(["you", "absolute", "muppet", "and", "twit"])
    profile = default_profile()  # beep all profanity
    client = ScanFake({"muppet", "twit"})

    # Pretend index 2 ("muppet") is already covered by an earlier pass.
    edits = build_scanned_edits(t, profile, client=client, pad_sec=0.0,
                                exclude_indices={2})
    words = {e.word for e in edits}
    assert words == {"twit"}            # muppet excluded
    assert edits[0].source == "model"
    assert edits[0].style == "beep"
    assert abs(edits[0].start - t[4].start) < 1e-9


# ---- coercion ---------------------------------------------------------------

def test_coerce_flagged_accepts_shapes():
    assert _coerce_flagged({"flagged": [{"index": 1}]}) == [{"index": 1}]
    assert _coerce_flagged([{"index": 1}]) == [{"index": 1}]
    assert _coerce_flagged({"index": 1, "word": "x"}) == [{"index": 1, "word": "x"}]
    assert _coerce_flagged("nonsense") == []
