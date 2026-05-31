# FoFo-Censor — Requirements & Design Document

**App name:** FoFo-Censor
**Status:** v1 design spec, ready for implementation planning
**Author intent:** Local-first, privacy-first tool that produces a "radio edit" of video content — censoring objectionable *expression* while preserving narrative, context, and authorial intent (including satire and stereotype where it is the point). Runs entirely on local hardware.
**Audience:** Claude Code, for planning and implementation.

---

## 1. Purpose & Philosophy

FoFo-Censor takes a video file the user legally owns and produces a filtered copy suitable for a less permissive viewer (canonical test case: showing *The Boondocks* to a religious-but-not-fragile parent).

Governing principle: **censor expression, preserve meaning.**

- **Default action is the radio edit.** Profanity and slurs are handled at the word level. The scene, dialogue cadence, comic timing, and satirical content all survive.
- **Cutaways are the exception.** A scene is only cut/replaced when it contains *visual* content that audio editing cannot address: realistic gore/violence, or nudity/explicit sexual content.
- **Context is never filtered.** If a line or scene means something to the story, it stays — only the hard-line expression (the specific word, the explicit visual) is suppressed.
- **Authorial intent is respected.** Stereotype, edgy satire, and shocking-but-non-explicit content are preserved by design. This is a profanity/explicit-content filter, not a sanitizer of ideas.

This keeps the problem largely **deterministic** (word-level audio edits) with a small **fuzzy** surface (visual scene judgment), holding cost and complexity low.

---

## 2. Goals & Non-Goals

### Goals (v1)
- Process local video files (mkv, mp4, etc.) into a filtered output file.
- Word-level audio censoring with multiple styles, configurable per content category — including a **safe-word replacement** mode (§7a).
- Optional visual pass that cuts away only from genuinely explicit visual content.
- Human-in-the-loop preview before final render, driven by a polished **TUI** (§11a).
- Portable, cacheable **filter map sidecar** (JSON) describing every edit.
- A prepended **legal/disclaimer card** on every generated output (§12).
- High-quality, space-efficient **export encoding** (§10a).
- Run entirely against a local OpenAI-compatible endpoint. No cloud, no telemetry.
- Profile-driven behavior with shippable starter profiles.

### Non-Goals (v1)
- No browser extension / streaming integration (Phase 2, §14).
- No DRM circumvention, ever. Input must be an unencrypted file the user already has.
- No distribution of filtered output (legally significant — see §3, §12).
- No real-time playback filtering (offline render only).
- No attempt to "fix" content where filtering would gut it; instead, warn the user (§10, coverage warning).

---

## 3. Legal Constraints (must inform architecture)

Hard design constraints, not footnotes:

- **Family Movie Act of 2005** permits private-home filtering of an **authorized copy** with **no permanent filtered copy distributed.** v1 is personal-use only.
- The tool operates on **files the user already possesses.** It never decrypts, rips, or circumvents protection. (VidAngel was killed on DMCA anti-circumvention grounds, not on filtering itself.)
- The **filter map sidecar contains only timestamps and decisions — no copyrighted content** — and is therefore safe to share/cache. This is the legally clean unit of reuse and the foundation for Phase 2.
- Rendered output is for the user who owns the source. No "share rendered file" feature.
- Every output carries a prepended disclaimer card stating the basis of lawful use (§12).

---

## 4. Hardware & Runtime Environment

| Component | Detail |
|---|---|
| Inference box | "INFINITY" — single RTX 4090, **power-limited** (one PCIe power connector, ~half power budget) |
| Vision+text model | **Qwen3.6-27B** (image-text-to-text + native video understanding), served via TurboQuant, ~180K context |
| Inference endpoint | OpenAI-compatible API at `http://192.168.1.99:8080/v1` |
| Transcription | Whisper (local — faster-whisper or whisper.cpp), word-level timestamps required |
| TTS | Kokoro (local, high quality) for cutaway narration AND safe-word replacement |
| Media processing | ffmpeg + PySceneDetect, local. ffmpeg build must include the chosen encoders (libsvtav1 / libx265 / NVENC) |

**Critical hardware implication — sequential staging, not concurrency.** A single power-limited 4090 cannot comfortably co-host Whisper, Qwen3.6, and Kokoro in VRAM at once. The pipeline **stages** work: transcribe → free Whisper → run model analysis → free model → run TTS → render. Optimize for *fewer, batched* model calls over real-time throughput. Provide a CPU-Whisper fallback if VRAM is tight.

**Qwen3.6 capabilities to exploit (confirmed from model card):**
- `image_url` content blocks → per-keyframe scene judgment.
- `video_url` content blocks with frame-sampling (`fps`, `do_sample_frames`) → short-clip judgment for ambiguous shots.
- ~180K usable context → an entire episode's transcript fits in one holistic-context call.
- Thinking mode on by default; set `enable_thinking: false` for fast deterministic classification.

---

## 5. System Architecture (high level)

```
                          ┌─────────────────────────────┐
                          │   TUI / CLI / Orchestrator   │
                          └──────────────┬──────────────┘
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
       ┌──────▼──────┐           ┌───────▼────────┐         ┌───────▼────────┐
       │  PROBE      │           │  AUDIO PIPE     │         │  VISUAL PIPE    │
       │  ffprobe    │           │  (deterministic)│         │  (fuzzy, opt-in)│
       │  fingerprint│           └───────┬────────┘         └───────┬────────┘
       └─────────────┘                   │                          │
                                  ┌───────▼────────┐         ┌───────▼────────┐
                                  │ Whisper STT     │        │ PySceneDetect   │
                                  │ word timestamps │        │ shot boundaries │
                                  └───────┬────────┘         └───────┬────────┘
                                          │                          │
                                  ┌───────▼────────┐         ┌───────▼────────┐
                                  │ Word classifier │        │ Qwen3.6 vision  │
                                  │ lists + Qwen    │        │ keyframe/clip   │
                                  │ (disambiguation)│        │ judgment        │
                                  └───────┬────────┘         └───────┬────────┘
                                          │                          │
                          ┌───────────────▼──────────────────────────▼───────────┐
                          │              DECISION ENGINE                          │
                          │   maps detections → actions per active PROFILE        │
                          │   (safe-word text generated here via Qwen)            │
                          └───────────────────────┬──────────────────────────────┘
                                                  │
                                          ┌───────▼────────┐
                                          │  FILTER MAP     │  ← cacheable, shareable,
                                          │  sidecar (JSON) │     content-free export
                                          └───────┬────────┘
                                                  │
                                          ┌───────▼────────┐
                                          │ TUI PREVIEW /   │  ← human confirms visual
                                          │ REVIEW          │     edits, edits summaries,
                                          └───────┬────────┘     auditions safe-words
                                                  │
                                          ┌───────▼────────┐
                                          │  TTS (Kokoro)   │  ← renders cutaway narration
                                          │                 │     + safe-word clips
                                          └───────┬────────┘
                                                  │
                                          ┌───────▼────────┐
                                          │  RENDERER       │  ← prepend disclaimer card,
                                          │  ffmpeg         │     apply edits, encode efficient
                                          └───────┬────────┘
                                                  │
                                          ┌───────▼────────┐
                                          │ OUTPUT FILE +   │
                                          │ updated sidecar │
                                          └────────────────┘
```

**Key architectural decisions:**
1. **One multimodal model** (Qwen3.6) for transcript-context judgment, visual judgment, AND safe-word/cutaway text generation. Whisper (STT) and Kokoro (TTS) are the only other models.
2. **Sidecar-first.** Analysis produces a filter map; rendering only ever consumes one. Separates *deciding* from *doing*: resumable, auditable, Phase-2-ready.
3. **Audio is deterministic; visual is reviewed.** Word edits don't need per-edit review; visual cutaways and (optionally) safe-word auditions pass through the TUI gate before render.
4. **Staged GPU use** to respect the single power-limited 4090.

---

## 6. Pipeline Workflows

### 6.1 Probe / Fingerprint
1. `ffprobe`: duration, resolution, frame rate, audio/subtitle track inventory.
2. Compute a content fingerprint (metadata + duration + sampled frame hashes) so a filter map can be matched back to a source later. Store in sidecar `source`.
3. If multiple audio tracks exist, select one (default first; CLI override).

### 6.2 Audio Pipeline (always on — the 95% path)
1. Extract target audio track to working wav (ffmpeg).
2. Whisper with **word-level timestamps** → `{word, start, end, confidence}`.
3. **Stage 1 — deterministic match** against categorized lists (profanity tiers, slurs, sexual terms). Direct hits flagged with category + tier. No model call. Catches the vast majority.
4. **Stage 2 — contextual disambiguation (Qwen3.6, batched, optional)** only for: homographs ("ass" insult vs. animal), list-boundary/low-confidence words, and a holistic whole-transcript pass tagging segments where censoring would damage meaning (so the renderer keeps edits word-scoped and never over-mutes). Slurs are never un-flagged.
5. Each flagged word → an `audio_edit` with start/end, category, tier, and resolved `style` from the active profile. If style is `safe_replace`, the decision engine also generates replacement text (§7a).

### 6.3 Visual Pipeline (opt-in — the 5% path)
1. PySceneDetect → shots `{shot_id, start, end}`.
2. Per shot, extract representative keyframe(s) (scene-change-aligned).
3. **Tier-1 (cheap):** keyframe(s) as `image_url` → Qwen3.6 visual-classification prompt → `{violence_level, sexual_level, confidence, description}`.
4. **Tier-2 (only ambiguous/low-confidence):** short clip as `video_url`, low `fps`, for a motion-aware second opinion. Gated to limit GPU cost.
5. Shots crossing a profile threshold → `visual_edit` candidates.
6. For cutaway candidates, request a clean one-sentence **cutaway summary** from Qwen3.6.

### 6.4 Decision Engine
- Consumes detections + active profile → typed edits in the filter map.
- Resolves action precedence: audio edits are word-scoped and independent; visual edits pick one action (`cutaway` > `blackbar` > `blur`).
- For `safe_replace` audio edits, generates replacement text via Qwen3.6 (§7a) and queues TTS jobs.
- Computes **coverage stats** (§10).

### 6.5 TTS Stage (Kokoro)
- Batch-synthesize all required clips: cutaway narrations and safe-word replacements.
- Each clip is fitted to its target window (§7a fit strategy). Cache clips keyed by text+voice so re-renders are free.

### 6.6 Preview / Review (TUI)
- Presents every `visual_edit`: thumbnail path, time range, model judgment, confidence, proposed action, editable `summary_text`.
- For `safe_replace` audio edits (optionally, if `--review-audio`): shows original word → proposed safe word, lets the user edit or audition the TTS clip.
- User can confirm, change action, edit text, or reject. Overrides written back to sidecar. Nothing renders until visual edits are resolved.

### 6.7 Render
- Reads the finalized filter map only.
- **Prepend disclaimer card** (§12) as the first segment.
- **Audio edits:** apply per-edit style at exact word timestamps:
  - `beep` / `silence` / `reverse` / `muffle`: DSP on the audio segment.
  - `safe_replace`: silence the original word window, insert the fitted Kokoro clip.
- **Visual edits:** `blur`/`blackbar` apply a video filter over the time range; `cutaway` replaces the shot's video span with a generated card (black slate + on-screen `summary_text`) and its audio with the Kokoro narration, then continues.
- **Encode** to the efficient export format (§10a), mux, and emit output + finalized sidecar.

---

## 7. Data Schemas

JSON; types indicative. Claude Code should formalize with Pydantic.

### 7.1 Filter Map (sidecar) — `<sourcename>.fofocensor.json`
Central artifact. Content-free apart from local-only audit fields (`word`, `description`) which are stripped in the shareable export.

```jsonc
{
  "fofocensor_version": "1.0",
  "created_utc": "ISO-8601",
  "source": {
    "filename": "string", "duration_sec": "number", "resolution": "WxH",
    "fps": "number", "fingerprint": "hash-string", "audio_track_index": "int"
  },
  "profile": { "name": "string", "snapshot": { /* full resolved profile, for reproducibility */ } },
  "models": {
    "transcription": "whisper-large-v3", "vision_text": "qwen3.6-27b",
    "tts": "kokoro", "endpoint": "http://192.168.1.99:8080/v1", "prompt_version": "string"
  },
  "audio_edits": [
    {
      "id": "string", "start": "number(sec)", "end": "number(sec)",
      "word": "string",                        // local-only audit; stripped in shareable export
      "category": "profanity|slur|sexual_term",
      "tier": "mild|moderate|severe",
      "style": "beep|silence|reverse|muffle|safe_replace",
      "replacement_text": "string|null",       // when style = safe_replace
      "tts_clip": "path|null",                  // cached synthesized clip
      "source": "list|model", "model_confidence": "number|null"
    }
  ],
  "visual_edits": [
    {
      "id": "string", "shot_id": "string", "start": "number(sec)", "end": "number(sec)",
      "detected": { "violence_level": "none|stylized|realistic|implied",
                    "sexual_level": "none|suggestive|explicit",
                    "confidence": "number(0-1)", "tier_used": "image|video",
                    "description": "string" },   // local-only; stripped in shareable export
      "action": "cutaway|blackbar|blur|none",
      "summary_text": "string|null", "tts_clip": "path|null",
      "user_confirmed": "boolean", "user_overridden": "boolean"
    }
  ],
  "coverage": {
    "total_edits": "int", "audio_edit_count": "int", "visual_edit_count": "int",
    "filtered_runtime_sec": "number", "filtered_runtime_pct": "number",
    "by_category": { "profanity": "int", "slur": "int", "sexual_term": "int",
                     "realistic_violence": "int", "explicit_sexual": "int" }
  }
}
```

> **Shareable export:** strips `audio_edits[].word`, `visual_edits[].detected.description`, and `tts_clip` paths, keeping only timestamps, categories, styles, and actions. This is the Phase-2-safe unit.

### 7.2 Profile — `<name>.profile.json`
```jsonc
{
  "name": "religious-mom",
  "description": "Bleep profanity + slurs; cut away only from realistic gore and explicit sexual content. Preserve satire and stereotype.",
  "audio": {
    "categories": {
      "profanity": { "act_on": ["mild","moderate","severe"],
                     "style": { "mild": "reverse", "moderate": "reverse", "severe": "beep" } },
      "slur":      { "act_on": ["all"], "style": "beep" },
      "sexual_term": { "act_on": ["moderate","severe"], "style": "reverse" }
    },
    "wordlists": ["base_profanity", "base_slurs", "base_sexual"],
    "preserve_context_segments": true
  },
  "safe_replace": {                              // used when any style = safe_replace
    "tone": "comedic|neutral|family",            // hint for the LLM replacement writer
    "fit_strategy": "timestretch|pad|natural",   // how the TTS clip fits the word window
    "max_timestretch_pct": 25,
    "match_syllables": true                       // prefer replacements close in length
  },
  "visual": {
    "enabled": true,
    "violence": { "stylized": "none", "implied": "none", "realistic": "cutaway" },
    "sexual":   { "suggestive": "none", "explicit": "cutaway" },
    "tier2_video_when_confidence_below": 0.7
  },
  "cutaway": { "card_style": "black_slate_centered_text", "narrate": true,
               "min_card_sec": 2.5, "max_card_sec": 8.0 },
  "tts": { "engine": "kokoro", "voice": "string-id", "rate": 1.0 },
  "disclaimer": { "enabled": true, "narrate": false, "dwell_sec": "auto",
                  "text_ref": "default" },        // default text in §12, overridable
  "render": {
    "export_mode": "efficient|fast",              // efficient = re-encode small; fast = stream-copy when possible
    "video_codec": "hevc|av1|h264",
    "encoder": "nvenc|software",                  // nvenc = fast (4090); software = best space
    "quality": "number",                          // CRF/CQ; see §10a defaults
    "audio_codec": "aac|opus",
    "container": "mp4|mkv"
  }
}
```

### 7.3 Word List — `<name>.wordlist.json`
```jsonc
{
  "name": "base_profanity", "language": "en",
  "entries": [ { "term": "string", "category": "profanity", "tier": "moderate",
                 "match": "exact|stem|regex", "context_sensitive": false } ]
}
```
- `context_sensitive: true` routes to Stage-2 model disambiguation instead of auto-flagging.
- Lists layer: base + user additions; user lists override/extend base.

### 7.4 Model I/O contracts (JSON-only responses)
- **Visual classification:** `{ "violence_level", "sexual_level", "confidence", "description" }`.
- **Cutaway summary:** `{ "summary": "string" }`.
- **Audio disambiguation (batched):** `[ { "word_id", "is_objectionable", "category", "tier", "meaning_bearing" } ]`.
- **Safe-word writer (batched):** `[ { "word_id", "replacement": "string" } ]` — given the original word, surrounding line, and profile `tone`/`match_syllables`, produce a clean replacement (§7a).
- Set `enable_thinking: false` for classification/replacement; keep thinking only for the holistic context pass if it measurably helps.

---

## 7a. Safe-Word Replacement (feature detail)

A per-category audio `style`. Instead of bleeping, the offending word is **replaced with a clean stand-in spoken by Kokoro TTS**, layered into the timeline where the original word was.

Mechanics:
1. **Generate replacement text.** The decision engine batches flagged `safe_replace` words to Qwen3.6 with the surrounding line, the profile `tone` (e.g., `comedic` → "fudge", "son of a biscuit", "motherflower"; `neutral` → "jerk", "shoot"; `family` → mild kid-safe terms), and `match_syllables` to prefer a length close to the original so it fits the gap and the cadence survives.
2. **Synthesize.** Kokoro renders the replacement clip; cache by text+voice.
3. **Fit to window.** Silence the original word's audio window, then place the clip per `fit_strategy`: `timestretch` (compress/expand clip within `max_timestretch_pct` to match the window), `pad` (center the clip, pad with silence), or `natural` (insert at the word start and let it run, nudging the window into adjacent silence if needed).
4. **Render.** The result is the character "saying" the clean word in a different voice — deliberately a bit janky, which is part of the appeal.

Expectations to set in docs/UX: the TTS voice will **not** match the character (no voice cloning in v1), lip-sync will not match, and timing fit is approximate. This is a feature, not a bug — it reliably turns the result comedic and is the explicit intent. The TUI lets the user audition and edit individual replacements (§6.6). Safe-word replacement works alongside beeping (mix styles per category), and slurs may still be forced to `beep` even when other categories use `safe_replace` (profile choice).

---

## 8. Decision Engine Logic (rules)
1. **Audio:** every list-matched or model-confirmed objectionable word → `audio_edit` with profile-resolved style (incl. `safe_replace`). No per-edit human review required.
2. **Context guard:** segments marked `meaning_bearing` still get word-level edits but are forbidden from escalating to scene-skip. Meaning is never removed, only specific words.
3. **Visual:** look up detected levels in the profile action maps; highest-severity mapping wins; one action per shot. `none` → no edit.
4. **Tier-2 escalation:** image-tier confidence < threshold → queue `video_url` re-judgment before finalizing.
5. **Coverage:** sum filtered runtime, compute pct, populate `coverage`; trigger warnings per §10.

---

## 9. Model Prompt Strategy (described, not coded)
Versioned prompts in `prompts/`; prompt version recorded in sidecar. Roles, all JSON-only output:
- **Visual judge** — rate `violence_level` (none / stylized cartoon / realistic-with-injury / implied-offscreen) and `sexual_level` (none / suggestive / explicit-or-nudity) + confidence + short factual description. Stylized/exaggerated violence is **not** flagged; only realistic harm or actual nudity/explicit acts.
- **Cutaway writer** — one clean factual sentence describing the shot, no profanity/explicit detail, audience = an adult following the plot.
- **Audio disambiguator (batched)** — per-word objectionability, category, tier, and meaning-bearing flag. Slurs never un-flagged.
- **Safe-word writer (batched)** — clean replacement per word, honoring `tone` and `match_syllables` (§7a).

---

## 10. Coverage Warning (the "Boondocks guard")
Before render, if `coverage.filtered_runtime_pct` exceeds a profile threshold (e.g., 40%), warn:
> "This profile would modify ~X% of this title. The result may be choppy or lose meaning. Continue / adjust profile / pick different content?"

Pure word-level edits don't reduce runtime, so the hard warning is driven mostly by visual cutaways/skips; a high *count* of audio edits triggers a softer "heads up, heavily censored" notice. Turns the failure mode (language-dependent content like *The Boondocks* at a strict profile) into informed consent rather than broken output.

## 10a. Export Encoding (recommendation)
Most edits are audio-only, but the design now prepends a disclaimer card and supports visual edits, so a clean **full re-encode is the sensible default** (stream-copy can't cleanly concatenate a generated card or apply video filters). Two modes:

- **`efficient` (default):** re-encode the whole output for space savings.
  - **Video codec — default HEVC (H.265):** best balance of high compression and broad device compatibility (most modern TVs/phones play it). Default quality CRF ~22 (software libx265) / CQ ~24 (NVENC). Offer **AV1** (SVT-AV1 software CRF ~30, or NVENC AV1 on the 4090's Ada encoder) for maximum space savings when the playback target supports it — flag the slightly weaker device compatibility. **H.264** as the universal-compatibility fallback.
  - **Encoder choice:** `software` (libx265 / SVT-AV1) gives the best size-per-quality and is the recommendation when space is the priority; **`nvenc`** is much faster on the 4090 with slightly larger files — recommend it for quick iterations and large batches. Make it a profile toggle.
  - **Audio:** AAC ~160 kbps for MP4 (compatibility) or Opus ~96–128 kbps for MKV (efficiency).
  - **Container:** MP4 default (compatibility); MKV optional (better for chapters/subtitle tracks).
- **`fast`:** stream-copy video where there are no visual edits and re-encode audio only — fastest, preserves original codec/size. Note: even in fast mode the prepended disclaimer card forces a re-encode of at least the leading segment, or a codec/parameter-matched concat; the implementation should handle this gracefully (simplest correct path: re-encode in `efficient` mode by default).

---

## 11. CLI Surface (v1)
- `fofo-censor analyze <input> --profile <name> [--visual] [--audio-track N] [--out-map path]`
- `fofo-censor preview <map>` — reopen the TUI review on an existing map.
- `fofo-censor render <input> --map <map> [--out <file>]`
- `fofo-censor run <input> --profile <name> [...]` — analyze → preview → render.
- `fofo-censor profiles list|show|init`
- Design for **resumability:** `analyze` and `render` are separable so a long analyze run on the contended GPU is done once and rendered cheaply.

## 11a. TUI (Terminal UI)
A polished interactive terminal interface (recommended: **Textual** for interaction + **Rich** for formatting). Requirements:
- **Structured, attractive layout** with clear sections, panels, color, and tasteful emoji (status: ✅ ⚠️ 🎬 🔊 ✂️).
- **Profile picker** and run launcher (select input, profile, toggle visual pass).
- **Live progress** during analyze/render: staged progress bars (transcribe → classify → visual → TTS → encode) fed by the orchestrator's structured logging.
- **Review screen** (the §6.6 gate): a navigable list of visual edits with thumbnails (or thumbnail paths), model judgment, confidence, and selectable actions; inline editing of cutaway summaries; for safe-word edits, original→replacement with edit + audition.
- **Coverage report** with the §10 warning surfaced prominently before render.
- Keyboard-driven selection/confirm; non-interactive `--yes` flag for headless runs that accept all model decisions.

---

## 12. Disclaimer Card (prepended to every output)
The renderer prepends a black-slate card (and optional Kokoro narration via `disclaimer.narrate`) before the feature begins. `dwell_sec: auto` scales hold time to reading length. Text is overridable per profile; the shipped default:

> **This is a filtered version, created for private home viewing.**
>
> This version was generated by FoFo-Censor from a copy the viewer is authorized to access, for private viewing in the home, consistent with the personal content-filtering provisions of the Family Movie Act of 2005. No copy of this filtered version is distributed or sold.
>
> This is original third-party material. It was not created by FoFo-Censor and was not originally intended for all audiences. Offensive *expression* — profanity, slurs, and explicit visual content — has been censored. The underlying *meaning, message, and creative intent* of the work have been preserved and not altered.
>
> Even after filtering, this material may still not be suitable for all viewers. Viewer discretion is advised.

Notes: keep it clearly worded but not framed as legal advice; the renderer should treat the exact text as data (in `prompts/` or a `disclaimers/` resource), versioned alongside prompts. The card is always present and not user-suppressible in v1 (it is part of the legal posture), though its wording is editable.

---

## 13. Dependencies & Environment (completeness)
- **Python 3.11+**, Pydantic (schemas), Rich + Textual (TUI), `openai` client (endpoint), httpx (retries/timeouts).
- **ffmpeg / ffprobe** built with `libx265`, `libsvtav1`, and NVENC support; **PySceneDetect**.
- **faster-whisper** (CTranslate2) or **whisper.cpp**; word-level timestamps required.
- **Kokoro** TTS + its runtime deps.
- Verify the inference endpoint is reachable and the model id at startup; fail fast with a clear TUI message if not.

## 13a. Configuration, Paths, Caching, Logging
- Config dir (XDG, e.g. `~/.config/fofo-censor/`): `profiles/`, `wordlists/`, `prompts/`, `disclaimers/`.
- Cache dir (e.g. `~/.cache/fofo-censor/`): TTS clips (keyed by text+voice), extracted keyframes, working audio. Cache makes re-renders cheap.
- Sidecar written next to the source (or to `--out-map`).
- Structured logging (JSON lines) that also feeds the TUI progress; `--verbose` and `--log-file`.
- Model calls: timeouts, bounded retries with backoff, and graceful degradation (e.g., if Stage-2 disambiguation fails, fall back to list-only results and note it in the sidecar).

---

## 14. Phase 2 (out of scope for v1, design for it now)
Browser extension / player overlay applying a **shareable filter map** in real time to a stream the user is **already legally watching**:
- Overlay-only: mute audio windows, draw black/blur rectangles, show cutaway cards on top of the playing video. **No copy, no DRM touch.**
- Consumes the **content-free** sidecar export (§7.1). Community-contributed maps become a network effect (like a subtitle database, for filter decisions) without distributing any media.
- Requires timing sync (match fingerprint/duration to the playing title; handle intro/ad offsets).
- Safe-word replacement in an overlay is harder (needs to inject audio and duck the stream) — likely beep/skip/cutaway only in Phase 2; safe-replace stays a render-time feature.
- Keep the sidecar format stable so Phase 2 is purely additive.

---

## 15. Risks & Open Questions
- **Visual judgment accuracy** — main quality risk; mitigated by TUI preview + Tier-2 video escalation; needs calibration on real clips.
- **GPU contention** on the single power-limited 4090 — confirm staged Whisper→Qwen→Kokoro sequencing doesn't OOM; CPU-Whisper fallback ready.
- **Whisper word-timestamp accuracy** on overlapping dialogue / music — may need padding around edits and around safe-word windows; evaluate.
- **Safe-word fit** — time-stretch limits vs. natural cadence; test the three fit strategies.
- **Style UX** — validate beep / silence / reverse / muffle / safe_replace on real content.
- **Slur policy** — currently always-bleep regardless of context and regardless of other categories using safe_replace; confirm per-title intent.
- **Export compatibility** — AV1 playback on the viewer's actual device (mom's TV); HEVC default hedges this.
- **Legal line** — personal-use only; disclaimer mandatory; no share-rendered-file feature.

---

## 16. Suggested Module Layout (for Claude Code planning)
```
fofo_censor/
  cli/                 # command surface
  tui/                 # Textual app: picker, progress, review, coverage
  probe/               # ffprobe wrapper, fingerprinting
  audio/
    transcribe/        # whisper integration, word timestamps
    classify/          # wordlists + Stage-2 model disambiguation
    safeword/          # safe-word text generation + fit logic
  visual/
    shots/             # PySceneDetect, keyframe extraction
    judge/             # Qwen3.6 image/video classification
    cutaway/           # summary generation
  tts/                 # Kokoro wrapper, clip cache, window fitting
  decision/            # decision engine, coverage stats
  filtermap/           # sidecar schema, load/save, public export
  render/              # ffmpeg edits, disclaimer card, cutaway cards, encode
  profiles/            # profile + wordlist schemas, starter profiles
  prompts/             # versioned model prompts
  disclaimers/         # disclaimer text resources
  model/               # OpenAI-compatible client, batching, retry
  config/              # paths, settings, logging
```

---

## 17. Build Phases / Milestones
1. **M1 — Audio-only MVP.** probe → Whisper → list-match → decision → render (one style) + disclaimer card + efficient encode. No model calls. Ships the 80%.
2. **M2 — Styles + profiles + sidecar + TUI shell.** All bleep styles, profile system, sidecar format, resumable analyze/render, basic TUI with progress.
3. **M3 — Safe-word replacement.** Qwen safe-word writer + Kokoro + window fitting + TUI audition/edit.
4. **M4 — Stage-2 audio disambiguation.** Context calls + meaning-bearing guard.
5. **M5 — Visual pass.** PySceneDetect → Qwen image judgment → cutaway gen → TUI review → render.
6. **M6 — Tier-2 video judgment + coverage warning + calibration** on real titles (Boondocks as stress test).
7. **(Phase 2) — Shareable map export + extension.**

---

*End of spec. Code-level design (libraries, function signatures, error handling, retry/batching specifics) is intentionally left to the implementation plan.*
