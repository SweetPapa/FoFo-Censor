"""Thin client over an OpenAI-compatible chat/completions endpoint (design §4, §7.4).

Targets the local inference box ("INFINITY"). Verified against an MLX server
serving `qwen3-vl-30b`: JSON-only output is requested via
`response_format={"type": "json_object"}`, and the model's default thinking mode
is disabled for deterministic classification via
`chat_template_kwargs={"enable_thinking": false}` (design §7.4).

All requests use bounded retries with exponential backoff (§13a).
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

log = logging.getLogger("fofo_censor.model")

DEFAULT_ENDPOINT = "http://192.168.1.99:8080/v1"
# INFINITY currently serves this (llama.cpp). The client also auto-adopts the
# single served model if the configured id isn't found, so this is just a label.
DEFAULT_MODEL = "Qwen3.6-27B-Q4_K_M.gguf"


@dataclass
class ModelConfig:
    endpoint: str = DEFAULT_ENDPOINT
    model: str = DEFAULT_MODEL
    timeout_sec: float = 120.0
    max_retries: int = 3
    temperature: float = 0.0
    enable_thinking: bool = False  # §7.4: off for classification/replacement

    @classmethod
    def from_env(cls) -> "ModelConfig":
        """Build config from env overrides so the endpoint isn't hardcoded.

        FOFO_ENDPOINT, FOFO_MODEL, FOFO_MODEL_TIMEOUT.
        """
        cfg = cls()
        if v := os.environ.get("FOFO_ENDPOINT"):
            cfg.endpoint = v
        if v := os.environ.get("FOFO_MODEL"):
            cfg.model = v
        if v := os.environ.get("FOFO_MODEL_TIMEOUT"):
            try:
                cfg.timeout_sec = float(v)
            except ValueError:
                pass
        return cfg


class ModelError(RuntimeError):
    pass


class ModelClient:
    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()

    def chat_json(
        self,
        messages: list[dict[str, Any]],
        *,
        enable_thinking: Optional[bool] = None,
        max_tokens: int = 2048,
    ) -> Any:
        """Send a chat request and return the parsed JSON-only response.

        `messages` follows the OpenAI chat format; `content` blocks may include
        `image_url` / `video_url` parts for the visual pipeline (§4). Raises
        `ModelError` if the endpoint is unreachable after retries or the reply
        isn't valid JSON.
        """
        think = self.config.enable_thinking if enable_thinking is None else enable_thinking
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            # Qwen thinking toggle (ignored by servers that don't support it).
            "chat_template_kwargs": {"enable_thinking": think},
        }
        text = self._post_with_retries("/chat/completions", payload)
        try:
            return self._extract_json(text)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ModelError(f"Model reply was not valid JSON: {text[:200]!r}") from exc

    def healthcheck(self) -> bool:
        """Return True if the endpoint is reachable and a usable model is served (§13).

        If the configured model id isn't in the served list but exactly one model
        is served (the common single-model llama.cpp/MLX case), adopt that id so
        the sidecar records what actually ran.
        """
        url = self.config.endpoint.rstrip("/") + "/models"
        try:
            resp = httpx.get(url, timeout=min(10.0, self.config.timeout_sec))
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            log.warning("Healthcheck failed: %s", exc)
            return False
        ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
        if self.config.model in ids:
            return True
        if len(ids) == 1:
            log.info("Model '%s' not served; adopting the only served model '%s'.",
                     self.config.model, ids[0])
            self.config.model = ids[0]
            return True
        log.warning("Model '%s' not served; available: %s", self.config.model, sorted(ids))
        return False

    # ---- internals ----------------------------------------------------------

    def _post_with_retries(self, path: str, payload: dict[str, Any]) -> str:
        url = self.config.endpoint.rstrip("/") + path
        last_exc: Optional[Exception] = None
        for attempt in range(self.config.max_retries):
            try:
                resp = httpx.post(url, json=payload, timeout=self.config.timeout_sec)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
                last_exc = exc
                wait = 0.5 * (2 ** attempt)
                log.warning("Model call attempt %d/%d failed: %s (retry in %.1fs)",
                            attempt + 1, self.config.max_retries, exc, wait)
                if attempt + 1 < self.config.max_retries:
                    time.sleep(wait)
        raise ModelError(f"Model endpoint failed after {self.config.max_retries} attempts: {last_exc}")

    @staticmethod
    def _extract_json(text: str) -> Any:
        """Parse a JSON object/array from a model reply, tolerating fences/prose.

        Prefers a clean parse; falls back to extracting the first balanced
        {...} or [...] span if the model wrapped it in stray text.
        """
        text = text.strip()
        # Strip ```json ... ``` fences if present.
        if text.startswith("```"):
            text = text.strip("`")
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Fallback: find the outermost JSON span.
        for opener, closer in (("[", "]"), ("{", "}")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start:end + 1])
        raise ValueError("No JSON found in model reply")
