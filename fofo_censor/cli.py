"""FoFo-Censor command-line interface (design §11).

Commands:
  analyze   — probe + transcribe + match -> filter-map sidecar (no render)
  render    — render a censored file from an existing sidecar
  run       — analyze then render (the one-shot path)
  transcribe— transcript-only sidecar (convenience)
  preview   — open the review TUI on a sidecar (stub)
  profiles  — list | show | init

Implemented today: the audio beep MVP (Whisper + wordlist + beep/silence/muffle).
Model-based stages, the visual pass, safe-word replacement, the disclaimer card,
and the TUI are scaffolded but not yet wired (they raise clear errors).
"""

from __future__ import annotations

import argparse
import os
import sys

from rich.console import Console

from . import __version__
from .audio.classify import Wordlist
from .audio.transcribe import transcribe_words
from .decision import build_audio_edits, build_disambiguated_edits, compute_coverage
from .decision.coverage import coverage_warning
from .filtermap import FilterMap, ModelSnapshot, ProfileRef, SourceInfo, to_shareable
from .probe import FFmpegNotFound, fingerprint_file, probe
from .profiles import (
    Profile,
    default_profile,
    init_starter_profiles,
    list_profiles,
    load_profile,
)
from .render import (
    RenderSettings,
    compute_dwell,
    default_disclaimer_text,
    default_output_path,
    render,
)

console = Console()


def _sidecar_path(input_path: str) -> str:
    base, _ext = os.path.splitext(input_path)
    return f"{base}.fofocensor.json"


def _load_wordlists(profile: Profile) -> Wordlist:
    lists = []
    for name in profile.audio.wordlists or ["base_profanity"]:
        try:
            lists.append(Wordlist.load_builtin(name))
        except (FileNotFoundError, ModuleNotFoundError, OSError):
            console.print(f"[yellow]Wordlist '{name}' not found; skipping.[/yellow]")
    if not lists:
        lists.append(Wordlist.load_builtin("base_profanity"))
    return Wordlist.merge(*lists) if len(lists) > 1 else lists[0]


def _transcribe_to_map(input_path: str, profile: Profile, args) -> FilterMap:
    info = probe(input_path)
    if not info.has_audio:
        console.print("[red]No audio track found in input.[/red]")
        raise SystemExit(2)

    console.print(f"[cyan]Transcribing[/cyan] with Whisper '{args.model}' on "
                  f"{args.device} ({args.compute_type})… "
                  f"[dim]first run downloads the model[/dim]")
    with console.status("Transcribing…", spinner="dots"):
        words = transcribe_words(
            input_path,
            model_size=args.model,
            device=args.device,
            compute_type=args.compute_type,
            audio_track_index=args.audio_track,
            vad_filter=not getattr(args, "no_vad", False),
        )
    console.print(f"[green]✓[/green] Transcribed [bold]{len(words)}[/bold] words "
                  f"({info.duration_sec:.1f}s).")

    return FilterMap(
        source=SourceInfo(
            filename=os.path.basename(input_path),
            duration_sec=info.duration_sec,
            resolution=f"{info.width}x{info.height}" if info.has_video else None,
            fps=info.fps or None,
            fingerprint=fingerprint_file(input_path),
            audio_track_index=args.audio_track,
        ),
        profile=ProfileRef(name=profile.name, snapshot=profile.model_dump()),
        models=ModelSnapshot(transcription=f"faster-whisper:{args.model}"),
        transcript=words,
    )


def _make_client(args):
    """Build a ModelClient from env + CLI overrides."""
    from .model import ModelClient, ModelConfig
    cfg = ModelConfig.from_env()
    if getattr(args, "endpoint", None):
        cfg.endpoint = args.endpoint
    if getattr(args, "model_id", None):
        cfg.model = args.model_id
    return ModelClient(cfg)


def _run_disambiguation(fmap: FilterMap, profile: Profile, wordlist, args) -> list:
    """Stage-2: route context-sensitive homographs through the model (§6.2 step 4)."""
    client = _make_client(args)
    console.print(f"[cyan]Disambiguating[/cyan] context-sensitive words via "
                  f"{client.config.model} @ {client.config.endpoint}…")
    if not client.healthcheck():
        console.print("[yellow]Model endpoint unreachable or model not served; "
                      "skipping Stage-2 (using list-only results).[/yellow]")
        return []
    try:
        extra = build_disambiguated_edits(
            fmap.transcript, wordlist, profile, client=client, pad_sec=args.pad
        )
    except Exception as exc:  # noqa: BLE001 - degrade gracefully (§13a)
        console.print(f"[yellow]Stage-2 disambiguation failed ({exc}); "
                      "using list-only results.[/yellow]")
        return []

    # Record model provenance in the sidecar.
    fmap.models.vision_text = client.config.model
    fmap.models.endpoint = client.config.endpoint
    fmap.models.prompt_version = "audio_disambiguator.v1"

    if extra:
        console.print(f"[green]Stage-2 confirmed {len(extra)} additional word(s):[/green] "
                      + ", ".join(sorted({e.word for e in extra})))
    else:
        console.print("[dim]Stage-2 added no edits.[/dim]")
    return extra


def _apply_decisions(fmap: FilterMap, profile: Profile, args) -> None:
    wordlist = _load_wordlists(profile)
    edits = build_audio_edits(fmap.transcript, wordlist, profile, pad_sec=args.pad)

    if getattr(args, "disambiguate", False):
        edits.extend(_run_disambiguation(fmap, profile, wordlist, args))

    if getattr(args, "style", None):
        for e in edits:
            e.style = args.style

    edits.sort(key=lambda e: e.start)
    fmap.audio_edits = edits

    if getattr(args, "visual", False):
        console.print("[yellow]--visual: the visual pass (M5) is not implemented "
                      "yet; skipping.[/yellow]")

    fmap.coverage = compute_coverage(fmap)

    if edits:
        console.print(f"[yellow]Flagged {len(edits)} word(s):[/yellow] "
                      + ", ".join(sorted({e.word for e in edits})))
    else:
        console.print("[green]No flagged words found.[/green]")

    warning = coverage_warning(fmap.coverage)
    if warning:
        console.print(f"[bold red]⚠ {warning}[/bold red]")


def _resolve_profile(name: str) -> Profile:
    try:
        return load_profile(name)
    except FileNotFoundError:
        console.print(f"[yellow]Profile '{name}' not found; using 'default'.[/yellow]")
        return default_profile()


def _disclaimer_from_snapshot(snapshot: dict, *, suppress: bool):
    """Resolve (disclaimer_text, dwell_sec) from a profile snapshot dict.

    The card is mandatory in v1 (§12); it is only omitted when a profile sets
    `disclaimer.enabled = false`, or via the dev-only `--no-disclaimer` flag.
    """
    if suppress:
        return None, None
    block = snapshot.get("disclaimer") if isinstance(snapshot, dict) else None
    block = block or {}
    if block.get("enabled") is False:
        return None, None

    text = block.get("text") or default_disclaimer_text()

    dwell_raw = block.get("dwell_sec", "auto")
    if isinstance(dwell_raw, (int, float)):
        dwell = float(dwell_raw)
    else:  # "auto" or unset
        dwell = compute_dwell(text)
    return text, dwell


def _render_settings_from_snapshot(snapshot: dict) -> RenderSettings:
    block = snapshot.get("render") if isinstance(snapshot, dict) else None
    return RenderSettings.from_profile_block(block)


# ---- commands ---------------------------------------------------------------

def cmd_transcribe(args) -> int:
    profile = default_profile()
    fmap = _transcribe_to_map(args.input, profile, args)
    out_map = args.out or _sidecar_path(args.input)
    fmap.save(out_map)
    console.print(f"[green]✓[/green] Wrote sidecar → [bold]{out_map}[/bold]")
    if args.show:
        for w in fmap.transcript:
            console.print(f"  [dim]{w.start:7.2f}–{w.end:6.2f}[/dim]  {w.word}")
    return 0


def cmd_analyze(args) -> int:
    profile = _resolve_profile(args.profile)
    fmap = _transcribe_to_map(args.input, profile, args)
    _apply_decisions(fmap, profile, args)
    out_map = args.out_map or _sidecar_path(args.input)
    fmap.save(out_map)
    console.print(f"[green]✓[/green] Wrote sidecar → [bold]{out_map}[/bold]")
    if args.export_share:
        import json
        share_path = out_map.replace(".json", ".share.json")
        with open(share_path, "w", encoding="utf-8") as fh:
            json.dump(to_shareable(fmap), fh, indent=2)
        console.print(f"[green]✓[/green] Wrote shareable export → [bold]{share_path}[/bold]")
    return 0


def cmd_render(args) -> int:
    fmap = FilterMap.load(args.map)
    snapshot = fmap.profile.snapshot or {}
    text, dwell = _disclaimer_from_snapshot(snapshot, suppress=args.no_disclaimer)
    settings = _render_settings_from_snapshot(snapshot)

    out = args.out or default_output_path(args.input)
    card_note = "with disclaimer card" if text else "no disclaimer card"
    console.print(f"[cyan]Rendering[/cyan] {len(fmap.audio_edits)} edit(s), "
                  f"{card_note} → {out}")
    with console.status("Encoding…", spinner="dots"):
        render(args.input, fmap.audio_edits, out,
               audio_track_index=fmap.source.audio_track_index,
               disclaimer_text=text, dwell_sec=dwell, render_settings=settings)
    console.print(f"[green]✓[/green] Done → [bold]{out}[/bold]")
    return 0


def cmd_run(args) -> int:
    profile = _resolve_profile(args.profile)
    if args.map:
        console.print(f"[cyan]Loading transcript[/cyan] from {args.map}")
        fmap = FilterMap.load(args.map)
    else:
        fmap = _transcribe_to_map(args.input, profile, args)
    _apply_decisions(fmap, profile, args)

    if args.keep_map:
        out_map = _sidecar_path(args.input)
        fmap.save(out_map)
        console.print(f"[dim]Sidecar → {out_map}[/dim]")

    if not args.yes and fmap.visual_edits:
        console.print("[yellow]Visual edits would need review (TUI not implemented); "
                      "re-run with --yes to accept all.[/yellow]")

    snapshot = profile.model_dump()
    text, dwell = _disclaimer_from_snapshot(snapshot, suppress=args.no_disclaimer)
    settings = _render_settings_from_snapshot(snapshot)

    out = args.out or default_output_path(args.input)
    card_note = "with disclaimer card" if text else "no disclaimer card"
    console.print(f"[cyan]Rendering[/cyan] ({card_note}) → {out}")
    with console.status("Encoding…", spinner="dots"):
        render(args.input, fmap.audio_edits, out,
               audio_track_index=fmap.source.audio_track_index,
               disclaimer_text=text, dwell_sec=dwell, render_settings=settings)
    console.print(f"[green]✓[/green] Done → [bold]{out}[/bold]")
    return 0


def cmd_preview(args) -> int:
    from .tui import run_tui
    return run_tui(args.map)


def cmd_profiles(args) -> int:
    if args.action == "list":
        for name in list_profiles():
            console.print(f"  {name}")
    elif args.action == "show":
        if not args.name:
            console.print("[red]profiles show requires a NAME.[/red]")
            return 2
        prof = load_profile(args.name)
        console.print_json(prof.model_dump_json())
    elif args.action == "init":
        written = init_starter_profiles()
        if written:
            for p in written:
                console.print(f"[green]✓[/green] {p}")
        else:
            console.print("Starter profiles already present.")
    return 0


# ---- parser -----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fofo-censor",
        description="Local-first video content filtering (audio beep MVP).",
    )
    p.add_argument("--version", action="version", version=f"fofo-censor {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def add_whisper_opts(sp):
        sp.add_argument("--model", default="small.en",
                        help="Whisper model (tiny.en, base.en, small.en (default), "
                             "medium.en, large-v3). Larger = more accurate, slower.")
        sp.add_argument("--device", default="cpu", help="cpu or cuda.")
        sp.add_argument("--compute-type", default="int8",
                        help="faster-whisper compute type (int8, float16, float32).")
        sp.add_argument("--audio-track", type=int, default=0, help="Audio track index.")
        sp.add_argument("--no-vad", action="store_true",
                        help="Disable voice-activity filtering (can recover words it clips).")

    def add_model_opts(sp):
        sp.add_argument("--disambiguate", action="store_true",
                        help="Stage-2: resolve context-sensitive words via the model endpoint.")
        sp.add_argument("--endpoint", help="OpenAI-compatible endpoint (default: env/INFINITY).")
        sp.add_argument("--model-id", help="Model id to request (default: env/qwen3-vl-30b).")

    t = sub.add_parser("transcribe", help="Transcript-only sidecar.")
    t.add_argument("input")
    t.add_argument("--out", help="Sidecar path (default: <input>.fofocensor.json).")
    t.add_argument("--show", action="store_true", help="Print the transcript.")
    add_whisper_opts(t)
    t.set_defaults(func=cmd_transcribe)

    a = sub.add_parser("analyze", help="Analyze to a filter-map sidecar (no render).")
    a.add_argument("input")
    a.add_argument("--profile", default="default")
    a.add_argument("--visual", action="store_true", help="(Not yet implemented.)")
    a.add_argument("--out-map", help="Sidecar path.")
    a.add_argument("--style", choices=["beep", "silence", "muffle"],
                   help="Override the profile's censor style for all edits.")
    a.add_argument("--pad", type=float, default=0.05)
    a.add_argument("--export-share", action="store_true",
                   help="Also write a content-free shareable sidecar.")
    add_whisper_opts(a)
    add_model_opts(a)
    a.set_defaults(func=cmd_analyze)

    r = sub.add_parser("render", help="Render a censored file from a sidecar.")
    r.add_argument("input")
    r.add_argument("--map", required=True, help="Filter-map sidecar to render.")
    r.add_argument("--out", help="Output media path.")
    r.add_argument("--no-disclaimer", action="store_true",
                   help="Dev/testing only: skip the disclaimer card (and stream-copy video).")
    r.set_defaults(func=cmd_render)

    rn = sub.add_parser("run", help="Analyze then render (one-shot).")
    rn.add_argument("input")
    rn.add_argument("--profile", default="default")
    rn.add_argument("--out", help="Output media path.")
    rn.add_argument("--map", help="Reuse an existing sidecar's transcript.")
    rn.add_argument("--visual", action="store_true", help="(Not yet implemented.)")
    rn.add_argument("--style", choices=["beep", "silence", "muffle"],
                    help="Override the profile's censor style for all edits.")
    rn.add_argument("--pad", type=float, default=0.05)
    rn.add_argument("--keep-map", action="store_true",
                    help="Write the sidecar next to the input.")
    rn.add_argument("--no-disclaimer", action="store_true",
                    help="Dev/testing only: skip the disclaimer card (and stream-copy video).")
    rn.add_argument("--yes", action="store_true", help="Accept all decisions (headless).")
    add_whisper_opts(rn)
    add_model_opts(rn)
    rn.set_defaults(func=cmd_run)

    pv = sub.add_parser("preview", help="Open the review TUI on a sidecar (stub).")
    pv.add_argument("map")
    pv.set_defaults(func=cmd_preview)

    pf = sub.add_parser("profiles", help="Manage profiles.")
    pf.add_argument("action", choices=["list", "show", "init"])
    pf.add_argument("name", nargs="?", help="Profile name (for 'show').")
    pf.set_defaults(func=cmd_profiles)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FFmpegNotFound as exc:
        console.print(f"[red]{exc}[/red]")
        return 3
    except NotImplementedError as exc:
        console.print(f"[yellow]Not implemented: {exc}[/yellow]")
        return 4
    except KeyboardInterrupt:
        console.print("\n[red]Interrupted.[/red]")
        return 130


if __name__ == "__main__":
    sys.exit(main())
