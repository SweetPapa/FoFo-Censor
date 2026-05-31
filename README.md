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

**Working today (M1 + parts of M2):**

```
ffprobe → Whisper word-level transcript → profile-driven wordlist match → ffmpeg beep/silence/muffle render
```

- probe + content fingerprint (§6.1)
- Whisper word timestamps (§6.2), local CPU by default — no GPU required
- deterministic wordlist matching with `exact`/`stem`/`regex` modes (§6.2, §7.3)
- profile system with per-category / per-tier styles + starter profile (§7.2)
- filter-map sidecar load/save + content-free shareable export (§7.1)
- decision engine + coverage stats with the "Boondocks guard" warning (§8, §10)
- `beep`, `silence`, `muffle` render styles (§6.7)
- resumable `analyze` / `render` split (§11)

**Scaffolded but not yet wired** (raise clear errors): the OpenAI-compatible
model client (`model/`), Stage-2 audio disambiguation (`audio/disambiguate.py`),
safe-word replacement + Kokoro TTS (`audio/safeword.py`, `tts/`), the visual
cutaway pass (`visual/`), the disclaimer/cutaway card renderers (`render/`), and
the review TUI (`tui/`). Versioned prompts live in `fofo_censor/prompts/`.

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

The first run downloads the chosen Whisper model. Larger models transcribe more
accurately (fewer missed or mis-timed words) at the cost of speed.

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

## How the beep render works

A single ffmpeg pass: the original audio is muted inside each flagged word window
via an expression-driven `volume` filter, a gated 1 kHz tone is summed in over the
same windows (`muffle` low-passes instead), and the video is **stream-copied** (no
re-encode). Speech outside the windows is untouched.

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
    disambiguate.py   # Stage-2 model disambiguation              [stub]
    safeword.py       # safe-word text gen + window fitting        [stub]
  visual/             # shots / judge / cutaway                    [stub]
  tts/                # Kokoro wrapper + clip cache                [stub]
  decision/           # decision engine + coverage stats         [done]
  render/
    beep.py           # ffmpeg beep/silence/muffle render          [done]
    disclaimer.py     # prepended legal card                       [stub]
    cutaway.py        # cutaway card                               [stub]
    encode.py         # codec/encoder arg builder                  [helper]
  model/              # OpenAI-compatible client                   [stub]
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
