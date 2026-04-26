"""クラウド LLM クライアント — Gemini と Groq の無料枠を 0 円で叩く。

両者とも以下の特徴で本研究に向く:
  - 無料枠で 100 試行以上 / 日が余裕で回せる
  - dated model id で pin 可能
  - temperature を明示指定可
  - stdlib (urllib) のみで実装可

無料枠の制約 (2026-04 時点、変動の可能性あり):
  Gemini: 15 req/min, 1500 req/day, 1M tokens/day  (gemini-2.0-flash 等)
  Groq:   30 req/min, 14400 req/day                (llama-3.3-70b-versatile 等)

API key 取得:
  Gemini: https://aistudio.google.com/apikey  (Google アカウントで即発行)
  Groq:   https://console.groq.com/keys       (登録 30 秒)

両方とも環境変数で渡す:
  GEMINI_API_KEY=AI...
  GROQ_API_KEY=gsk_...
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


# ---- 共通 ----------------------------------------------------------------

@dataclass
class CloudResponse:
    """各クライアント共通の戻り値。"""
    text: str
    model_id: str
    usage: dict[str, Any]
    wall_seconds: float
    raw: dict[str, Any]


def _post_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout: float = 120.0) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    # Groq は Python-urllib のデフォルト UA を Cloudflare 1010 で弾く。
    # 一般的なブラウザ UA を付けないと通らない。
    req = urllib.request.Request(url, data=data, headers={
        "content-type": "application/json",
        "user-agent": "paper1-benchmark/0.1 (python-urllib)",
        **headers,
    })
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            if e.code in (429, 500, 502, 503, 504) and attempt == 0:
                # rate-limit / transient: 1 回だけ待ち再試行
                time.sleep(2.5)
                continue
            raise RuntimeError(f"HTTP {e.code} from {url}: {body_text}") from e
    raise RuntimeError("unreachable")


# ---- Gemini -------------------------------------------------------------

class GeminiClient:
    """Google Gemini API (Generative Language API v1beta)。

    使用例:
        c = GeminiClient(model_id="gemini-2.0-flash-001")
        resp = c.ask("hello", temperature=0.0)

    モデル例 (無料枠で利用可):
        gemini-2.0-flash-001         (高速、推奨デフォルト)
        gemini-2.0-flash-thinking-exp-1219
        gemini-2.5-flash             (より新)
        gemini-2.5-pro               (上位、無料枠ありだが quota 厳しめ)
    """

    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, model_id: str, api_key: str | None = None):
        self.model_id = model_id
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY 未設定。https://aistudio.google.com/apikey で取得")

    def ask(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        seed: int | None = None,
        max_tokens: int = 512,
        system: str | None = None,
    ) -> CloudResponse:
        url = f"{self.BASE}/{self.model_id}:generateContent"
        body: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}], "role": "user"}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "text/plain",
            },
        }
        if seed is not None:
            body["generationConfig"]["seed"] = int(seed)
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        t0 = time.time()
        payload = _post_json(url, body, {"x-goog-api-key": self.api_key})
        wall = time.time() - t0

        text = ""
        for cand in payload.get("candidates", []):
            for part in (cand.get("content") or {}).get("parts", []):
                if "text" in part:
                    text += part["text"]

        return CloudResponse(
            text=text,
            model_id=self.model_id,
            usage=payload.get("usageMetadata", {}),
            wall_seconds=wall,
            raw=payload,
        )


# ---- Groq ---------------------------------------------------------------

class GroqClient:
    """Groq Cloud (OpenAI-compatible chat/completions API)。

    使用例:
        c = GroqClient(model_id="llama-3.3-70b-versatile")
        resp = c.ask("hello", temperature=0.0)

    モデル例 (無料枠で利用可、2026-04 時点):
        llama-3.3-70b-versatile             (バランス型推奨)
        llama-3.1-8b-instant                (軽量、超高速)
        qwen-qwq-32b                        (推論強化)
        deepseek-r1-distill-llama-70b       (DeepSeek-R1 蒸留版、思考連鎖)
        mixtral-8x7b-32768                  (旧、まだ動く)
    """

    BASE = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, model_id: str, api_key: str | None = None):
        self.model_id = model_id
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY 未設定。https://console.groq.com/keys で取得")

    def ask(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        seed: int | None = None,
        max_tokens: int = 512,
        system: str | None = None,
    ) -> CloudResponse:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if seed is not None:
            body["seed"] = int(seed)

        t0 = time.time()
        payload = _post_json(self.BASE, body, {"Authorization": f"Bearer {self.api_key}"})
        wall = time.time() - t0

        text = ""
        choices = payload.get("choices", [])
        if choices:
            text = (choices[0].get("message") or {}).get("content", "") or ""

        return CloudResponse(
            text=text,
            model_id=self.model_id,
            usage=payload.get("usage", {}),
            wall_seconds=wall,
            raw=payload,
        )


# ---- 統合 dispatcher ---------------------------------------------------

def make_client(provider: str, model_id: str):
    p = provider.lower()
    if p == "gemini":
        return GeminiClient(model_id)
    if p == "groq":
        return GroqClient(model_id)
    raise ValueError(f"unknown cloud provider {provider!r}; expected 'gemini' or 'groq'")
