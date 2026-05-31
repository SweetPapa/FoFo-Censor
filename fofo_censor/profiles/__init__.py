"""Profiles: behavior config + wordlist schemas, and starter profiles (design §7.2)."""

from .schema import Profile, AudioConfig, AudioCategory
from .loader import load_profile, list_profiles, init_starter_profiles, default_profile

__all__ = [
    "Profile",
    "AudioConfig",
    "AudioCategory",
    "load_profile",
    "list_profiles",
    "init_starter_profiles",
    "default_profile",
]
