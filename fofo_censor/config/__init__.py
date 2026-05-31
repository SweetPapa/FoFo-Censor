"""Configuration: XDG paths, caching locations, and logging setup (design §13a)."""

from .paths import AppPaths, app_paths
from .logging import setup_logging

__all__ = ["AppPaths", "app_paths", "setup_logging"]
