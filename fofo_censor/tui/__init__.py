"""Terminal UI (design §11a). STUB.

Planned (Textual + Rich): profile picker / run launcher, live staged progress
(transcribe → classify → visual → TTS → encode), the §6.6 review screen for
visual edits and safe-word auditions, and the §10 coverage report before render.
"""

from .app import run_tui

__all__ = ["run_tui"]
