"""Track A Phase 2 — LLM constellation の中央 registry.

Phase 1 (5 LLM) → Phase 2 (7 LLM) に拡張。
matrix runner や aggregator は本 registry を import するだけで
参加 LLM の一覧を取得できる。

LLM family 多様性 (Phase 2 時点):
  Meta:      llama-3.1-8b, llama-3.3-70b
  Alibaba:   qwen2.5:7b, qwen3-32b
  Microsoft: phi-4:14b      (★ Phase 2 新規)
  DeepSeek:  deepseek-r1:7b (★ Phase 2 新規)
  OpenAI:    gpt-oss-120b
  = 5 family

Reasoning 軸:
  reasoning:     qwen3-32b (大型), deepseek-r1:7b (小型)
  non-reasoning: 残り 5 体

Source 軸:
  Ollama local:  qwen2.5:7b, phi-4:14b, deepseek-r1:7b
  Groq cloud:    llama-3.1-8b, llama-3.3-70b, qwen3-32b, gpt-oss-120b
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMSpec:
    """1 LLM の static metadata (cell ID, 提供元, 容量, family など)."""
    tag: str                 # 短い識別子 (filename safe): qwen25-7b
    model_id: str            # provider 上の正式 id: qwen2.5:7b
    provider: str            # ollama / groq / anthropic
    family: str              # Meta / Alibaba / Microsoft / DeepSeek / OpenAI / Anthropic
    parameter_count_B: float # 公称パラメータ数 (Billion)
    is_reasoning: bool
    notes: str = ""


# ---------------------------------------------------------------------------
# Phase 1 で確定済みの 5 LLM
# ---------------------------------------------------------------------------

PHASE1_MODELS: list[LLMSpec] = [
    LLMSpec(
        tag="qwen25-7b",
        model_id="qwen2.5:7b",
        provider="ollama",
        family="Alibaba",
        parameter_count_B=7.6,
        is_reasoning=False,
        notes="negative control: 小型 + 決定論的だが物理不正確 (Phase 1 で実証)",
    ),
    LLMSpec(
        tag="llama31-8b",
        model_id="llama-3.1-8b-instant",
        provider="groq",
        family="Meta",
        parameter_count_B=8.0,
        is_reasoning=False,
        notes="negative control: 小型 + ecut=30 で未収束 (Phase 1 で実証)",
    ),
    LLMSpec(
        tag="llama33-70b",
        model_id="llama-3.3-70b-versatile",
        provider="groq",
        family="Meta",
        parameter_count_B=70.0,
        is_reasoning=False,
        notes="主軸: 大型、Phase 1 で convergence loose 内 + smearing soft_warn",
    ),
    LLMSpec(
        tag="gptoss-120b",
        model_id="openai/gpt-oss-120b",
        provider="groq",
        family="OpenAI",
        parameter_count_B=120.0,
        is_reasoning=False,
        notes="主軸: 最大、Phase 1 で完全合格",
    ),
    LLMSpec(
        tag="qwen3-32b",
        model_id="qwen/qwen3-32b",
        provider="groq",
        family="Alibaba",
        parameter_count_B=32.0,
        is_reasoning=True,
        notes="主軸: reasoning 大型、Phase 1 で完全合格 (ただし wall 大)",
    ),
]


# ---------------------------------------------------------------------------
# Phase 2 新規追加 (Ollama local 2 体)
# ---------------------------------------------------------------------------

PHASE2_NEW_MODELS: list[LLMSpec] = [
    LLMSpec(
        tag="phi4-14b",
        model_id="phi4:14b",
        provider="ollama",
        family="Microsoft",
        parameter_count_B=14.7,
        is_reasoning=False,
        notes="Phase 2 新規: 中型 dense、5B-32B ギャップを埋める。Microsoft family 追加",
    ),
    LLMSpec(
        tag="deepseekr1-7b",
        model_id="deepseek-r1:7b",
        provider="ollama",
        family="DeepSeek",
        parameter_count_B=7.0,
        is_reasoning=True,
        notes="Phase 2 新規: reasoning 小型 (qwen3-32b は reasoning 大型と対比)、DeepSeek family 追加",
    ),
]


# ---------------------------------------------------------------------------
# 集約
# ---------------------------------------------------------------------------

ALL_MODELS: list[LLMSpec] = PHASE1_MODELS + PHASE2_NEW_MODELS


def by_tag(tag: str) -> LLMSpec:
    for s in ALL_MODELS:
        if s.tag == tag:
            return s
    raise KeyError(f"no LLMSpec with tag={tag!r}")


def filter_by(
    provider: str | None = None,
    family: str | None = None,
    is_reasoning: bool | None = None,
) -> list[LLMSpec]:
    out = ALL_MODELS
    if provider:
        out = [s for s in out if s.provider == provider]
    if family:
        out = [s for s in out if s.family == family]
    if is_reasoning is not None:
        out = [s for s in out if s.is_reasoning == is_reasoning]
    return out


def families() -> list[str]:
    seen: dict[str, None] = {}
    for s in ALL_MODELS:
        seen[s.family] = None
    return list(seen.keys())
