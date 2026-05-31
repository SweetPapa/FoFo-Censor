"""XDG-style config and cache locations (design §13a).

  config dir : profiles/, wordlists/, prompts/, disclaimers/
  cache dir  : tts/ (clips keyed by text+voice), keyframes/, audio/

Honors XDG_CONFIG_HOME / XDG_CACHE_HOME, falling back to ~/.config and ~/.cache,
so it works the same on Linux and macOS. On Windows, APPDATA/LOCALAPPDATA are used.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_DIRNAME = "fofo-censor"


def _base(env: str, *default_parts: str) -> Path:
    val = os.environ.get(env)
    if val:
        return Path(val)
    if os.name == "nt":  # Windows
        appdata = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if appdata:
            return Path(appdata)
    return Path.home().joinpath(*default_parts)


@dataclass
class AppPaths:
    config_dir: Path
    cache_dir: Path

    @property
    def profiles_dir(self) -> Path:
        return self.config_dir / "profiles"

    @property
    def wordlists_dir(self) -> Path:
        return self.config_dir / "wordlists"

    @property
    def prompts_dir(self) -> Path:
        return self.config_dir / "prompts"

    @property
    def disclaimers_dir(self) -> Path:
        return self.config_dir / "disclaimers"

    @property
    def tts_cache_dir(self) -> Path:
        return self.cache_dir / "tts"

    @property
    def keyframes_cache_dir(self) -> Path:
        return self.cache_dir / "keyframes"

    @property
    def audio_cache_dir(self) -> Path:
        return self.cache_dir / "audio"

    def ensure(self) -> "AppPaths":
        for p in (
            self.profiles_dir, self.wordlists_dir, self.prompts_dir,
            self.disclaimers_dir, self.tts_cache_dir, self.keyframes_cache_dir,
            self.audio_cache_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)
        return self


def app_paths() -> AppPaths:
    config = _base("XDG_CONFIG_HOME", ".config") / APP_DIRNAME
    cache = _base("XDG_CACHE_HOME", ".cache") / APP_DIRNAME
    return AppPaths(config_dir=config, cache_dir=cache)
