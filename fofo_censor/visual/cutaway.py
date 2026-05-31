"""Cutaway summary generation (design §6.3 step 6, §7.4). STUB.

One clean factual sentence describing a cut shot — no profanity/explicit detail,
for an adult following the plot. JSON contract: { "summary": "string" }.
"""

from __future__ import annotations

from typing import Optional

from ..model import ModelClient
from .shots import Shot


def summarize_shot(shot: Shot, *, client: Optional[ModelClient] = None) -> str:
    raise NotImplementedError("Cutaway summary generation (M5) is not implemented.")
