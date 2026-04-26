"""Ollama local-server クライアント (stdlib のみ)。

Track A Phase 2 で 5 → 7 LLM に拡張するために、experiments/repro-v1/run.py
の中に embed されていた ``call_ollama`` を独立 client として切り出した。
``llm/cloud.py`` (Gemini/Groq) と同じ ``LLMResponse`` 形式で返すため、
Phase 2 の統一 matrix runner から一貫して呼べる。

サポート対象 (Phase 2):
  - qwen2.5:7b      (Phase 1 既存、negative control 小型)
  - phi-4:14b       (新規追加、Microsoft 中型枠)
  - deepseek-r1:7b  (新規追加、DeepSeek reasoning 小型枠)

API: ``http://localhost:11434/api/generate``
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any


OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"


@dataclass
class LLMResponse:
    """cloud.py の CloudResponse と同形式。"""
    text: str
    model_id: str
    usage: dict[str, Any]    # eval_count / eval_duration_s / load_duration_s
    wall_seconds: float
    raw: dict[str, Any]


class OllamaClient:
    def __init__(
        self,
        model_id: str,
        temperature: float = 0.0,
        seed: int | None = 42,
        num_predict: int = 512,
        timeout: float = 600.0,
    ):
        """``model_id`` は ``ollama list`` で見える tag (例: ``phi-4:14b``).

        ``num_predict`` は reasoning モデル (deepseek-r1, qwen3) では
        小さすぎると thinking が途中で切れる。Phase 1 で qwen3-32b の
        max_tokens=512 が truncation を引き起こした事故を踏まえ、
        Phase 2 では default 512 だが reasoning モデルは呼び出し側で
        2048 以上に上げる。
        """
        self.model_id = model_id
        self.temperature = temperature
        self.seed = seed
        self.num_predict = num_predict
        self.timeout = timeout

    def ask(self, prompt: str, override_num_predict: int | None = None) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self.model_id,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": override_num_predict or self.num_predict,
            },
        }
        if self.seed is not None:
            body["options"]["seed"] = int(self.seed)

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            OLLAMA_URL,
            data=data,
            headers={"content-type": "application/json"},
        )
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            payload = json.load(r)
        wall = time.time() - t0

        return LLMResponse(
            text=payload.get("response", ""),
            model_id=self.model_id,
            usage={
                "eval_count": payload.get("eval_count"),
                "eval_duration_s": (payload.get("eval_duration") or 0) / 1e9,
                "load_duration_s": (payload.get("load_duration") or 0) / 1e9,
                "prompt_eval_count": payload.get("prompt_eval_count"),
            },
            wall_seconds=wall,
            raw=payload,
        )


def list_installed_models() -> list[str]:
    """``ollama list`` の API 版。"""
    req = urllib.request.Request(OLLAMA_TAGS_URL)
    with urllib.request.urlopen(req, timeout=10.0) as r:
        d = json.load(r)
    return [m["name"] for m in d.get("models", [])]


def is_installed(model_id: str) -> bool:
    """tag 完全一致 (例: ``phi-4:14b``)。"""
    return model_id in list_installed_models()
