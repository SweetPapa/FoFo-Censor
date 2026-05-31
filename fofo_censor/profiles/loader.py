"""Load, list, and initialize profiles (design §11 `profiles` commands, §13a)."""

from __future__ import annotations

import json
import shutil
from importlib import resources
from pathlib import Path

from ..config import app_paths
from .schema import AudioCategory, AudioConfig, Profile

STARTER_PROFILES = ["religious-mom"]


def default_profile() -> Profile:
    """A built-in fallback profile: beep all profanity and slurs."""
    return Profile(
        name="default",
        description="Beep all profanity and slurs at every tier.",
        audio=AudioConfig(
            categories={
                "profanity": AudioCategory(act_on=["all"], style="beep"),
                "slur": AudioCategory(act_on=["all"], style="beep"),
                "sexual_term": AudioCategory(act_on=["all"], style="beep"),
            },
            wordlists=["base_profanity"],
        ),
    )


def _starter_text(name: str) -> str:
    return resources.files("fofo_censor.profiles.starter").joinpath(
        f"{name}.profile.json"
    ).read_text(encoding="utf-8")


def load_profile(name_or_path: str) -> Profile:
    """Load a profile by name (user dir, then built-in starters) or by file path."""
    p = Path(name_or_path)
    if p.suffix == ".json" and p.exists():
        return Profile.model_validate_json(p.read_text(encoding="utf-8"))

    if name_or_path == "default":
        return default_profile()

    # User config dir takes precedence over built-in starters.
    user_path = app_paths().profiles_dir / f"{name_or_path}.profile.json"
    if user_path.exists():
        return Profile.model_validate_json(user_path.read_text(encoding="utf-8"))

    if name_or_path in STARTER_PROFILES:
        return Profile.model_validate_json(_starter_text(name_or_path))

    raise FileNotFoundError(f"Profile '{name_or_path}' not found.")


def list_profiles() -> list[str]:
    """Names of available profiles: default + starters + user profiles."""
    names = {"default", *STARTER_PROFILES}
    pdir = app_paths().profiles_dir
    if pdir.exists():
        for f in pdir.glob("*.profile.json"):
            names.add(f.name.removesuffix(".profile.json"))
    return sorted(names)


def init_starter_profiles() -> list[Path]:
    """Copy built-in starter profiles into the user config dir (`profiles init`)."""
    paths = app_paths().ensure()
    written: list[Path] = []
    for name in STARTER_PROFILES:
        dest = paths.profiles_dir / f"{name}.profile.json"
        if not dest.exists():
            dest.write_text(_starter_text(name), encoding="utf-8")
            written.append(dest)
    return written
