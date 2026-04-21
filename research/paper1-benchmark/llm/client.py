"""Anthropic Messages API direct client, stdlib only.

Design choices (all intentional for Paper 1 reproducibility):

* ``model_id`` **must** be a dated id (e.g. ``claude-opus-4-7-20260419``).
  Bare ids like ``claude-opus-4-7`` are rejected because they silently
  follow the rolling alias and break provenance.
* ``temperature`` defaults to 0.0 for deterministic experiments. The
  caller can override, but we warn if >0 and seed is None.
* Every call writes a ``LLMEvent`` to the provided ``JsonlLog`` AND
  produces a provenance zip bundle. No "success" is returned unless both
  artefacts are on disk.
* No streaming, no retries beyond a single 5xx back-off. Flaky behaviour
  must surface — silently swallowing retries would corrupt the dataset.

Usage::

    from llm.client import AnthropicClient
    from orchestrator.provenance import JsonlLog, current_env

    c = AnthropicClient(model_id="claude-opus-4-7-20260419")
    env = current_env()
    with JsonlLog("results/llm.jsonl") as log:
        resp = c.ask(prompt, temperature=0.0, seed=42, log=log, bundle_dir="results/llm-bundles", env=env)
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.provenance import (
    JsonlLog,
    LLMEvent,
    RunEnv,
    bundle_llm_event,
    current_env,
    sha256_text,
)


DATED_MODEL_RE = re.compile(r"^claude-[a-z0-9-]+-\d{8}$")

ENDPOINT = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


@dataclass
class AnthropicClient:
    model_id: str
    api_key: str | None = None
    max_tokens: int = 2048
    user_agent: str = "paper1-benchmark/0.1"

    def __post_init__(self) -> None:
        if not DATED_MODEL_RE.match(self.model_id):
            raise ValueError(
                f"model_id {self.model_id!r} is not a dated id. "
                "Paper 1 requires pinning (e.g. claude-opus-4-7-20260419)."
            )
        self.api_key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. "
                "source ~/.config/paper1/anthropic.env first."
            )

    def ask(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        seed: int | None = None,
        system: str | None = None,
        log: JsonlLog | None = None,
        bundle_dir: str | Path | None = None,
        env: RunEnv | None = None,
        extra: dict[str, Any] | None = None,
    ) -> LLMEvent:
        if temperature > 0.0 and seed is None:
            # Loud warning to stderr — Paper 1 demands determinism.
            import sys as _sys
            print(
                f"[llm.client] WARN: temperature={temperature} with no seed — "
                "experiment will not be reproducible",
                file=_sys.stderr,
            )

        body: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": self.max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        # The public Anthropic API does not currently honour a `seed`
        # parameter for Claude models; we persist it in the event
        # metadata regardless, so retries can be matched.

        payload = self._post(body)
        response_text = _extract_text(payload)

        event = LLMEvent(
            prompt_sha=sha256_text(prompt),
            response_sha=sha256_text(response_text),
            model_id=self.model_id,
            temperature=temperature,
            seed=seed,
            prompt=prompt,
            response=response_text,
            usage=payload.get("usage", {}),
            extra={"api_response_id": payload.get("id", ""), **(extra or {})},
        )

        env = env or current_env()
        if log is not None:
            log.write({
                "kind": "llm",
                "schema": "paper3.provenance.llm.v1",
                "timestamp_utc": env.timestamp_utc,
                "repo_commit": env.repo_commit,
                **event.__dict__,
            })
        if bundle_dir is not None:
            bundle_llm_event(Path(bundle_dir), event, env=env)

        return event

    # ------------------------------------------------------------ transport
    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            ENDPOINT,
            data=data,
            headers={
                "x-api-key": self.api_key or "",
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
                "user-agent": self.user_agent,
            },
        )
        # Single retry on 5xx; do not retry 4xx (client error, won't fix
        # itself).
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code >= 500 and attempt == 0:
                    time.sleep(2.0)
                    continue
                body_text = e.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Anthropic API HTTP {e.code}: {body_text}") from e
        raise RuntimeError("unreachable")


def _extract_text(payload: dict[str, Any]) -> str:
    """Pull all ``text`` content blocks out of a Messages response."""
    parts: list[str] = []
    for block in payload.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)
