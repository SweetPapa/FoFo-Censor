# FoFo-Censor

Local-first video content filtering. Produces a "radio edit" of video you legally
own — censoring objectionable *expression* while preserving meaning. Everything
runs locally; no cloud, no telemetry.

See [`FoFo-Censor-DESIGN.md`](FoFo-Censor-DESIGN.md) for the full intended system.

## Status

**Cross-platform Python** (macOS / Linux / Windows). The full package skeleton
from the design doc (§16) is in place; the audio beep path is fully working, and
the remaining stages are scaffolded with stable interfaces and clear
`NotImplementedError`s so they drop in milestone by milestone.

**Working today (M1 + M2 + M4):**

```
ffprobe → Whisper word-level transcript → Stage-1 wordlist match
        → Stage-2 model disambiguation (optional) → profile decision
        → ffmpeg beep/silence/muffle render + prepended disclaimer card
```

- probe + content fingerprint (§6.1)
- Whisper word timestamps (§6.2); default model `small.en`, local CPU — no GPU required
- deterministic wordlist matching with `exact`/`stem`/`regex` modes (§6.2, §7.3)
- **Stage-2 contextual disambiguation** of context-sensitive homographs via a
  local OpenAI-compatible endpoint (§6.2 step 4, §7.4); slurs are never un-flagged
- profile system with per-category / per-tier styles + starter profile (§7.2)
- filter-map sidecar load/save + content-free shareable export (§7.1)
- decision engine + coverage stats with the "Boondocks guard" warning (§8, §10)
- `beep`, `silence`, `muffle` render styles (§6.7)
- **mandatory disclaimer card** prepended to every output, with reading-time
  auto-dwell and per-profile wording (§12)
- **full re-encode + concat export** with profile-driven codec/encoder/quality
  (HEVC / AV1 / H.264, software or NVENC) (§10a)
- resumable `analyze` / `render` split (§11)

**Scaffolded but not yet wired** (raise clear errors): safe-word replacement +
Kokoro TTS (`audio/safeword.py`, `tts/`), the visual cutaway pass (`visual/`,
`render/cutaway.py`), and the review TUI (`tui/`). The `reverse` and
`safe_replace` audio styles are downgraded to `beep` with a warning until
implemented. Versioned prompts live in `fofo_censor/prompts/`.

### Stage-2 disambiguation

`--disambiguate` routes context-sensitive wordlist hits (homographs like "ass"
the insult vs. the animal) to a local model for an in-context yes/no, so they're
only censored when actually objectionable. Configure the endpoint via
`--endpoint` / `--model-id` or the `FOFO_ENDPOINT` / `FOFO_MODEL` env vars
(defaults: `http://192.168.1.99:8080/v1`, `qwen3-vl-30b`). If the endpoint is
unreachable the analysis degrades gracefully to list-only results.

```bash
fofo-censor analyze input.mp4 --profile religious-mom --disambiguate
```

The only external requirement is `ffmpeg`/`ffprobe` on your PATH. The inference
endpoint URL and NVENC/encoder choices are config/profile-driven, so nothing ties
the code to one machine.

## Install

Requires Python 3.11+ and ffmpeg.

```bash
# ffmpeg:  macOS: brew install ffmpeg | Debian/Ubuntu: apt install ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Use

```bash
# One-shot: transcribe, match against a profile, and render a censored copy
fofo-censor run input.mp4 --profile religious-mom --out clean.mp4 --yes

# Or split it (resumable — analyze once on a slow box, render cheaply):
fofo-censor analyze input.mp4 --profile religious-mom --export-share
fofo-censor render input.mp4 --map input.fofocensor.json --out clean.mp4

# Transcript-only sidecar
fofo-censor transcribe input.mp4 --show

# Profiles
fofo-censor profiles list
fofo-censor profiles show religious-mom
fofo-censor profiles init        # copy starter profiles into your config dir
```

Useful flags:

| flag | meaning |
|---|---|
| `--profile` | profile name (`default`, `religious-mom`, or your own) or a `.profile.json` path |
| `--model` | Whisper size: `tiny.en`, `base.en` (default), `small.en`, `medium`, `large-v3` |
| `--device` / `--compute-type` | `cpu`/`int8` (default) or `cuda`/`float16` for GPU |
| `--style` | override the profile and force `beep` / `silence` / `muffle` for all edits |
| `--pad SECONDS` | padding around each flagged word (default 0.05) |
| `--map PATH` | reuse an existing sidecar (skip re-transcription) |
| `--export-share` | also write a content-free shareable sidecar |
| `--disambiguate` | enable Stage-2 model disambiguation (analyze/run) |
| `--endpoint` / `--model-id` | override the model endpoint / id |
| `--no-vad` | disable voice-activity filtering (recovers words VAD clips) |

The first run downloads the chosen Whisper model. The default is `small.en`;
`medium.en` and `large-v3` transcribe more accurately (fewer missed or mis-timed
words) at the cost of speed. If words are still missed, also try `--no-vad`.

> Profile styles `reverse` and `safe_replace` are defined in the schema but not
> yet implemented; the renderer downgrades them to `beep` with a warning so a
> full profile still renders.

## Wordlists

Built-in: `fofo_censor/data/wordlists/base_profanity.json`. Format (design §7.3):

```json
{
  "name": "base_profanity",
  "entries": [
    { "term": "damn", "category": "profanity", "tier": "mild", "match": "exact" },
    { "term": "shit", "category": "profanity", "tier": "moderate", "match": "stem" }
  ]
}
```

`match` is `exact` (normalized equality), `stem` (token starts with term — catches
inflections), or `regex` (full-match regex). A profile lists which wordlists to
load; lists layer (later entries extend earlier ones).

Add `"context_sensitive": true` to an entry to route it to Stage-2 model
disambiguation instead of auto-flagging — used for homographs ("ass", "bloody",
"prick") that are only sometimes profanity. These are skipped entirely unless
`--disambiguate` is on.

## How rendering works

The censor itself is an expression-driven ffmpeg filter: the original audio is
muted inside each flagged word window via a `volume` expression, a gated 1 kHz
tone is summed in over the same windows (`muffle` low-passes instead).

Because every output carries a mandatory disclaimer card (§12) and a generated
card can't be stream-copied in, the standard path **re-encodes** in a single
ffmpeg pass: it builds a black-slate card (`color` + `drawtext`, dwell scaled to
reading length), normalizes the censored feature, and `concat`s card + feature
into one HEVC/AV1/H.264 file per the profile's `render` block (§10a). The card is
not user-suppressible in v1; `--no-disclaimer` exists for development only and
falls back to the fast stream-copy audio path.

## Project layout (design §16)

```
fofo_censor/
  cli.py              # analyze / render / run / transcribe / preview / profiles
  probe/              # ffprobe wrapper + content fingerprint
  config/             # XDG paths, caching dirs, structured logging
  filtermap/          # pydantic sidecar schema + shareable export
  audio/
    transcribe.py     # faster-whisper word timestamps          [done]
    classify.py       # wordlists + deterministic matching        [done]
    disambiguate.py   # Stage-2 model disambiguation              [done]
    safeword.py       # safe-word text gen + window fitting        [stub]
  visual/             # shots / judge / cutaway                    [stub]
  tts/                # Kokoro wrapper + clip cache                [stub]
  decision/           # decision engine + coverage stats         [done]
  render/
    pipeline.py       # orchestrator: card + censor, one ffmpeg pass [done]
    beep.py           # ffmpeg beep/silence/muffle audio filter      [done]
    disclaimer.py     # prepended legal card (drawtext + dwell)       [done]
    encode.py         # codec/encoder/quality arg builder            [done]
    cutaway.py        # cutaway card                                 [stub]
  model/              # OpenAI-compatible client (httpx + retries)  [done]
  profiles/           # profile schema, loader, starter profiles  [done]
  prompts/            # versioned model prompts (§9)
  disclaimers/        # disclaimer text resources (§12)
  tui/                # Textual review UI                          [stub]
  data/wordlists/     # built-in base_profanity.json
tests/                # unit tests (no ffmpeg/whisper needed)
```

## Tests

```bash
pip install pytest
pytest
```

## Legal

Personal-use filtering of a copy you are authorized to access (Family Movie Act of
2005). No DRM circumvention; no distribution of filtered output. See design §3/§12.
