"""Stage-2 disambiguation tests using a fake client (no network)."""

from fofo_censor.audio.classify import Wordlist
from fofo_censor.audio.disambiguate import (
    build_context,
    collect_candidates,
    disambiguate,
)
from fofo_censor.decision import build_audio_edits, build_disambiguated_edits
from fofo_censor.filtermap.schema import WordToken
from fofo_censor.model.client import ModelClient
from fofo_censor.profiles import default_profile


def _parse_candidates(user_content: str):
    """Extract the candidates JSON array that follows the 'CANDIDATES:' marker."""
    import json
    marker = "CANDIDATES:"
    body = user_content[user_content.index(marker) + len(marker):]
    start = body.find("[")
    return json.loads(body[start:body.rfind("]") + 1])


def _wordlist():
    return Wordlist.from_dict({
        "name": "t",
        "entries": [
            {"term": "damn", "category": "profanity", "tier": "mild", "match": "exact"},
            {"term": "ass", "category": "profanity", "tier": "moderate",
             "match": "exact", "context_sensitive": True},
            {"term": "nword", "category": "slur", "tier": "severe",
             "match": "exact", "context_sensitive": True},
        ],
    })


class FakeClient:
    """Stands in for ModelClient.chat_json; records prompts, returns canned JSON."""

    def __init__(self, decision_by_word):
        self.decision_by_word = decision_by_word
        self.calls = []

    def healthcheck(self):
        return True

    def chat_json(self, messages, *, enable_thinking=None, max_tokens=2048):
        self.calls.append(messages)
        results = []
        for it in _parse_candidates(messages[-1]["content"]):
            verdict = self.decision_by_word.get(it["word"].lower(), False)
            results.append({
                "word_id": it["word_id"],
                "is_objectionable": verdict,
                "category": "profanity",
                "tier": "moderate",
                "meaning_bearing": False,
            })
        return {"results": results}


def _transcript():
    # "kick his ass" (insult) ... then later "the ass brayed" (animal).
    # The two occurrences are spaced well beyond the context window so the
    # second one's context cannot see the word "kick".
    filler = ["and", "then", "much", "later", "on", "that", "very",
              "same", "quiet", "afternoon", "outside"]
    words = ["kick", "his", "ass"] + filler + ["the", "ass", "brayed"]
    return [WordToken(word=w, start=i * 0.3, end=i * 0.3 + 0.2)
            for i, w in enumerate(words)]


# ---- candidate collection ---------------------------------------------------

def test_collect_only_context_sensitive_nonslur():
    wl = _wordlist()
    transcript = [
        WordToken(word="damn", start=0, end=0.3),      # plain hit, not collected
        WordToken(word="ass", start=0.4, end=0.6),     # context-sensitive -> collected
        WordToken(word="nword", start=0.7, end=0.9),   # slur -> never routed
    ]
    cands = collect_candidates(transcript, wl)
    words = [c.token.word for c in cands]
    assert words == ["ass"]


def test_build_context_marks_target():
    transcript = _transcript()
    ctx = build_context(transcript, 2, window=2)
    assert "«ass»" in ctx
    assert "kick" in ctx and "his" in ctx


# ---- disambiguate via fake client -------------------------------------------

def test_disambiguate_returns_decisions_keyed_by_word_id():
    wl = _wordlist()
    cands = collect_candidates(_transcript(), wl)
    assert len(cands) == 2
    client = FakeClient(decision_by_word={"ass": True})
    decisions = disambiguate(cands, client=client)
    assert set(decisions) == {c.word_id for c in cands}
    assert all(d["is_objectionable"] for d in decisions.values())


def test_build_disambiguated_edits_keeps_only_objectionable():
    wl = _wordlist()
    profile = default_profile()  # acts on profanity at all tiers, beep
    transcript = _transcript()

    # Model says the FIRST "ass" (insult) is objectionable, but it sees both with
    # the same word text -> our fake flags all "ass". Use index-aware fake.
    class IndexFake(FakeClient):
        def chat_json(self, messages, *, enable_thinking=None, max_tokens=2048):
            results = []
            for it in _parse_candidates(messages[-1]["content"]):
                # objectionable only when context contains "kick" (the insult)
                obj = "kick" in it["context"]
                results.append({"word_id": it["word_id"], "is_objectionable": obj,
                                "category": "profanity", "tier": "moderate"})
            return {"results": results}

    edits = build_disambiguated_edits(transcript, wl, profile,
                                      client=IndexFake({}), pad_sec=0.0)
    assert len(edits) == 1
    assert edits[0].source == "model"
    # The insult is the first "ass" (index 2 -> start 0.6); the animal is left alone.
    assert abs(edits[0].start - 0.6) < 1e-9


def test_stage1_and_stage2_are_disjoint():
    """Stage-1 ignores context-sensitive; Stage-2 only handles those."""
    wl = _wordlist()
    profile = default_profile()
    transcript = [
        WordToken(word="damn", start=0, end=0.3),
        WordToken(word="ass", start=0.4, end=0.6),
    ]
    s1 = build_audio_edits(transcript, wl, profile, pad_sec=0.0)
    assert {e.word for e in s1} == {"damn"}

    client = FakeClient(decision_by_word={"ass": True})
    s2 = build_disambiguated_edits(transcript, wl, profile, client=client, pad_sec=0.0)
    assert {e.word for e in s2} == {"ass"}


# ---- JSON extraction --------------------------------------------------------

def test_extract_json_plain():
    assert ModelClient._extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_code_fence():
    assert ModelClient._extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_with_surrounding_prose():
    assert ModelClient._extract_json('Sure! [1, 2, 3] done') == [1, 2, 3]
