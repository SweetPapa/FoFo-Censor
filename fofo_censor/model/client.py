"""Thin client over an OpenAI-compatible chat/completions endpoint.

STUB: the request shape and JSON-only contracts (design §7.4) are defined here so
downstream modules can be written against a stable interface, but the actual HTTP
call is not yet wired. Implementing `chat_json` (with httpx + bounded retries) is
the entry point for the M3/M4/M5 model features.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

DEFAULT_ENDPOINT = "http://192.168.1.99:8080/v1"
DEFAULT_MODEL = "qwen3.6-27b"


@dataclass
class ModelConfig:
    endpoint: str = DEFAULT_ENDPOINT
    model: str = DEFAULT_MODEL
    timeout_sec: float = 120.0
    max_retries: int = 3
    enable_thinking: bool = False  # §7.4: off for classification/replacement


class ModelClient:
    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()

    def chat_json(self, messages: list[dict[str, Any]], *,
                  enable_thinking: Optional[bool] = None) -> Any:
        """Send a chat request and parse a JSON-only response.

        `messages` follows the OpenAI chat format; `content` blocks may include
        `image_url` / `video_url` parts for the visual pipeline (§4).
        """
        raise NotImplementedError(
            "ModelClient.chat_json is not implemented yet. Wire this to the "
            f"OpenAI-compatible endpoint at {self.config.endpoint} (httpx + retries)."
        )

    def healthcheck(self) -> bool:
        """Verify the endpoint is reachable and the model id is served (§13)."""
        raise NotImplementedError("Endpoint healthcheck not implemented yet.")

    @staticmethod
    def _extract_json(text: str) -> Any:
        """Best-effort parse of a JSON object/array from a model reply."""
        return json.loads(text)
