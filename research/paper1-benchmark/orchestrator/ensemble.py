"""Track A Phase 2 — LLM Ensemble post-hoc 集計 (4 手法).

Step 4 main の (5 LLM × 10 材料 × N=10 trials) 結果を入力に、
4 ensemble 手法で「集計後 params」を算出し、個別 LLM 結果と比較する。

Phase 2 では追加 DFT を実行しない (2026-04-26 user 判断) ため、
本モジュールは **既存 LLM 提案データのみ** から:
  - ensemble param-set 自体
  - ensemble 内部一致度 (4 手法間で同じ params に落ちるか)
  - 個別 LLM の提案分布との比較
を計算する。物理検証 (DFT 結果との一致) は Phase 3 で行う。

実装する 4 手法:
  (A) param-wise voting: 各 param を独立に 5 LLM の最頻 mode で集計
  (B) accuracy-weighted: 各 LLM に accuracy weight を付け加重平均 (leave-one-out)
  (C) guardrail + voting: 物理制約フィルタ後に (A) と同じ集計
  (E) MoE 材料ルーティング: Tier 別に最良 LLM を選び virtual ensemble

入力データ形状:
  experiments/step4-main/results/{model_tag}/{material_slug}/summary.json
    schema: paper3.step4-main.v1
    キー: mode_params (LLM の N=10 trial mode), n_valid, etc.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# データロード
# ---------------------------------------------------------------------------

@dataclass
class CellSummary:
    """1 (LLM, material) cell の Step 4 main 結果."""
    model_tag: str
    model_family: str
    model_size_B: float
    is_reasoning: bool
    material_slug: str
    material_formula: str
    material_tier: str
    n_valid: int
    mode_params: dict[str, Any] | None
    unique_param_set_count: int
    fully_reproducible_params: bool


def load_step4_summaries(results_dir: Path) -> list[CellSummary]:
    """experiments/step4-main/results/ 配下の全 summary.json を読み込む."""
    out: list[CellSummary] = []
    for summary_path in results_dir.rglob("summary.json"):
        d = json.loads(summary_path.read_text())
        if d.get("n_valid", 0) == 0:
            continue   # 全失敗 cell は除外
        out.append(
            CellSummary(
                model_tag=d["model_tag"],
                model_family=d.get("model_family", ""),
                model_size_B=d.get("model_size_B", 0.0),
                is_reasoning=d.get("is_reasoning", False),
                material_slug=d["material_slug"],
                material_formula=d["material_formula"],
                material_tier=d["material_tier"],
                n_valid=d["n_valid"],
                mode_params=d.get("mode_params"),
                unique_param_set_count=d.get("unique_param_set_count", 0),
                fully_reproducible_params=d.get("fully_reproducible_params", False),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Ensemble (A) parameter-wise voting
# ---------------------------------------------------------------------------

NUMERIC_KEYS = ("ecutwfc", "ecutrho", "degauss", "conv_thr", "mixing_beta")
LIST_KEYS = ("kpoints",)
CATEGORICAL_KEYS = ("smearing",)


def ensemble_A_voting(cells_for_material: list[CellSummary]) -> dict[str, Any] | None:
    """5 LLM の mode_params を集約: 数値は中央値、カテゴリは最頻、リストは要素別中央値."""
    valid = [c for c in cells_for_material if c.mode_params is not None]
    if not valid:
        return None

    out: dict[str, Any] = {}
    for k in NUMERIC_KEYS:
        vals = [float(c.mode_params[k]) for c in valid if k in c.mode_params]
        out[k] = statistics.median(vals) if vals else None
    for k in CATEGORICAL_KEYS:
        vals = [c.mode_params[k] for c in valid if k in c.mode_params]
        if vals:
            out[k] = Counter(vals).most_common(1)[0][0]
    for k in LIST_KEYS:
        # kpoints: 要素別中央値 (整数化)
        lists = [c.mode_params[k] for c in valid if k in c.mode_params]
        if lists:
            length = len(lists[0])
            out[k] = [int(statistics.median([l[i] for l in lists])) for i in range(length)]
    out["_ensemble_method"] = "A_voting"
    out["_n_contributing"] = len(valid)
    return out


# ---------------------------------------------------------------------------
# Ensemble (B) accuracy-weighted average
# ---------------------------------------------------------------------------

def ensemble_B_weighted(
    cells_for_material: list[CellSummary],
    accuracy_weights: dict[str, float],
) -> dict[str, Any] | None:
    """各 LLM に accuracy weight を付け加重平均.

    accuracy_weights: model_tag → 重み (合計 1 でなくて良い、内部正規化)。
    leave-one-out で各 cell の評価時には自分自身を除外して weight 計算する
    こともできるが、ここでは事前計算した weight を渡す形に簡略化。
    """
    valid = [
        c for c in cells_for_material
        if c.mode_params is not None and c.model_tag in accuracy_weights
    ]
    if not valid:
        return None

    weights = [accuracy_weights[c.model_tag] for c in valid]
    total_w = sum(weights)
    if total_w == 0:
        return None

    out: dict[str, Any] = {}
    for k in NUMERIC_KEYS:
        vals = [(float(c.mode_params[k]), w) for c, w in zip(valid, weights) if k in c.mode_params]
        if vals:
            out[k] = sum(v * w for v, w in vals) / sum(w for _, w in vals)
    for k in CATEGORICAL_KEYS:
        # カテゴリは weight 重みつき投票
        votes: dict[str, float] = {}
        for c, w in zip(valid, weights):
            if k in c.mode_params:
                votes[c.mode_params[k]] = votes.get(c.mode_params[k], 0) + w
        if votes:
            out[k] = max(votes.items(), key=lambda x: x[1])[0]
    for k in LIST_KEYS:
        lists = [(c.mode_params[k], w) for c, w in zip(valid, weights) if k in c.mode_params]
        if lists:
            length = len(lists[0][0])
            out[k] = [
                int(round(sum(l[i] * w for l, w in lists) / sum(w for _, w in lists)))
                for i in range(length)
            ]
    out["_ensemble_method"] = "B_weighted"
    out["_n_contributing"] = len(valid)
    out["_weights_used"] = {c.model_tag: accuracy_weights[c.model_tag] for c in valid}
    return out


# ---------------------------------------------------------------------------
# Ensemble (C) guardrail + voting
# ---------------------------------------------------------------------------

# 物理制約 — Phase 1/2 の経験則から
GUARDRAIL_RULES = {
    "ecutwfc_min_Ry": 20.0,         # SG15 PBE-1.2 で最低限必要
    "ecutwfc_max_Ry": 200.0,        # 過剰 cutoff 排除
    "ecutrho_to_ecutwfc_ratio_min": 4.0,   # norm-conserving 制約
    "degauss_max_Ry_for_insulator": 0.02,  # 0.27 eV 以上は gap を潰す
    "kpoint_min": 2,                # 1×1×1 は単点計算で SCF 不安定
    "kpoint_max": 16,               # 過剰 k 排除
    "mixing_beta_min": 0.1,
    "mixing_beta_max": 1.0,
    "conv_thr_min": 1e-12,
    "conv_thr_max": 1e-5,
}

INSULATOR_FORBIDDEN_SMEARINGS = {
    "fermi-dirac", "fd", "mp", "methfessel-paxton", "mv", "marzari-vanderbilt"
}


def passes_guardrails(params: dict[str, Any], is_insulator: bool) -> bool:
    """物理制約に通るかチェック."""
    if not params:
        return False
    try:
        ecut = float(params["ecutwfc"])
        if ecut < GUARDRAIL_RULES["ecutwfc_min_Ry"]: return False
        if ecut > GUARDRAIL_RULES["ecutwfc_max_Ry"]: return False
        ecutrho = float(params["ecutrho"])
        if ecutrho < ecut * GUARDRAIL_RULES["ecutrho_to_ecutwfc_ratio_min"]: return False
        for kp in params["kpoints"]:
            if kp < GUARDRAIL_RULES["kpoint_min"] or kp > GUARDRAIL_RULES["kpoint_max"]:
                return False
        beta = float(params["mixing_beta"])
        if beta < GUARDRAIL_RULES["mixing_beta_min"] or beta > GUARDRAIL_RULES["mixing_beta_max"]:
            return False
        thr = float(params["conv_thr"])
        if thr < GUARDRAIL_RULES["conv_thr_min"] or thr > GUARDRAIL_RULES["conv_thr_max"]:
            return False
        if is_insulator:
            smearing = str(params.get("smearing", "")).lower().strip()
            if smearing in INSULATOR_FORBIDDEN_SMEARINGS:
                return False
            degauss = float(params.get("degauss", 0))
            if degauss > GUARDRAIL_RULES["degauss_max_Ry_for_insulator"]:
                return False
    except (KeyError, ValueError, TypeError):
        return False
    return True


def ensemble_C_guardrail(
    cells_for_material: list[CellSummary],
    is_insulator: bool,
) -> dict[str, Any] | None:
    """guardrail フィルタ後に (A) と同じ集計."""
    survivors = [
        c for c in cells_for_material
        if c.mode_params is not None and passes_guardrails(c.mode_params, is_insulator)
    ]
    if not survivors:
        return {"_ensemble_method": "C_guardrail",
                "_n_contributing": 0,
                "_n_filtered_out": len(cells_for_material),
                "_failure": "no LLM passed guardrails"}

    out = ensemble_A_voting(survivors) or {}
    out["_ensemble_method"] = "C_guardrail"
    out["_n_contributing"] = len(survivors)
    out["_n_filtered_out"] = len(cells_for_material) - len(survivors)
    return out


# ---------------------------------------------------------------------------
# Ensemble (E) MoE 材料ルーティング
# ---------------------------------------------------------------------------

def ensemble_E_moe(
    cells_for_material: list[CellSummary],
    tier_best_model: dict[str, str],
) -> dict[str, Any] | None:
    """材料 Tier に応じて事前選定した最良 LLM の mode_params をそのまま使う.

    tier_best_model: e.g., {"A": "gptoss-120b", "B": "qwen3-32b", "C": "llama33-70b"}
    """
    if not cells_for_material:
        return None
    tier = cells_for_material[0].material_tier
    chosen_model_tag = tier_best_model.get(tier)
    if not chosen_model_tag:
        return {"_ensemble_method": "E_moe", "_failure": f"no model assigned for tier {tier}"}

    chosen = next((c for c in cells_for_material if c.model_tag == chosen_model_tag), None)
    if not chosen or chosen.mode_params is None:
        return {"_ensemble_method": "E_moe", "_failure": f"chosen model {chosen_model_tag} has no valid mode_params"}

    out = dict(chosen.mode_params)
    out["_ensemble_method"] = "E_moe"
    out["_chosen_model"] = chosen_model_tag
    out["_n_contributing"] = 1
    out["_tier"] = tier
    return out


# ---------------------------------------------------------------------------
# 集約 — 全材料 × 4 手法
# ---------------------------------------------------------------------------

@dataclass
class EnsembleReport:
    material_slug: str
    material_formula: str
    material_tier: str
    individual_cells: list[CellSummary]
    ensemble_A: dict[str, Any] | None
    ensemble_B: dict[str, Any] | None
    ensemble_C: dict[str, Any] | None
    ensemble_E: dict[str, Any] | None
    cross_method_agreement: float          # 0-1: 4 ensemble 手法間の params 一致度

    def to_dict(self) -> dict[str, Any]:
        return {
            "material_slug": self.material_slug,
            "material_formula": self.material_formula,
            "material_tier": self.material_tier,
            "n_individual_LLMs": len(self.individual_cells),
            "ensembles": {
                "A_voting": self.ensemble_A,
                "B_weighted": self.ensemble_B,
                "C_guardrail": self.ensemble_C,
                "E_moe": self.ensemble_E,
            },
            "cross_method_agreement": self.cross_method_agreement,
        }


def cross_method_agreement(
    ens_list: list[dict[str, Any] | None],
) -> float:
    """4 ensemble 手法が **同じ ecutwfc + smearing + kpoints** を出した割合.

    シンプルな 3-key 一致率。完全一致なら 1.0、全部バラバラなら 0.0。
    """
    valid = [
        e for e in ens_list
        if e and "ecutwfc" in e and "smearing" in e and "kpoints" in e
    ]
    if len(valid) < 2:
        return 0.0
    keys = [
        (round(float(e["ecutwfc"]), 2), str(e["smearing"]), tuple(e["kpoints"]))
        for e in valid
    ]
    counter = Counter(keys)
    most_common, _count = counter.most_common(1)[0]
    return _count / len(valid)


def build_reports(
    cells: list[CellSummary],
    accuracy_weights: dict[str, float],
    insulator_map: dict[str, bool],
    tier_best_model: dict[str, str],
) -> list[EnsembleReport]:
    """全材料について 4 ensemble 手法を計算."""
    by_mat: dict[str, list[CellSummary]] = {}
    for c in cells:
        by_mat.setdefault(c.material_slug, []).append(c)

    reports: list[EnsembleReport] = []
    for slug, group in by_mat.items():
        is_insulator = insulator_map.get(group[0].material_formula, True)
        a = ensemble_A_voting(group)
        b = ensemble_B_weighted(group, accuracy_weights)
        c = ensemble_C_guardrail(group, is_insulator)
        e = ensemble_E_moe(group, tier_best_model)
        agreement = cross_method_agreement([a, b, c, e])
        reports.append(
            EnsembleReport(
                material_slug=slug,
                material_formula=group[0].material_formula,
                material_tier=group[0].material_tier,
                individual_cells=group,
                ensemble_A=a,
                ensemble_B=b,
                ensemble_C=c,
                ensemble_E=e,
                cross_method_agreement=agreement,
            )
        )
    return reports
