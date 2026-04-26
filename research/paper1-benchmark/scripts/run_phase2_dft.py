"""Track A Phase 2 — Step 4 main DFT trigger.

Step 4 main の (LLM, material) cell の mode_params を ai-param-experiment.yml
の predictions/{tag}.json 形式に変換し、必要なら gh workflow run でトリガする。

ai-param-experiment.yml は ``research/paper1-benchmark/experiments/{exp_id}/predictions/*.json``
を読み、各 cell ごとに pw.x 実行 → bundle zip を artifact として上げる。

入力:
    experiments/step4-main/results/{model_tag}/{material_slug}/summary.json

出力:
    experiments/phase2-main-dft/predictions/{model_tag}-{material_slug}.json
    experiments/phase2-main-dft/predictions/{material_slug}-{ensemble_method}.json
    materials/fixtures/ にシンボリックリンク (workflow が探す形に整える)

使い方:
    python3 scripts/run_phase2_dft.py --emit-only         # JSON 生成のみ (push しない)
    python3 scripts/run_phase2_dft.py --include-ensemble  # ensemble 結果も含む
    python3 scripts/run_phase2_dft.py --trigger           # JSON 生成 + git push + workflow trigger
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from orchestrator.ensemble import (
    load_step4_summaries, build_reports,
    ensemble_A_voting, ensemble_B_weighted, ensemble_C_guardrail, ensemble_E_moe,
)

STEP4_RESULTS = REPO_ROOT / "experiments" / "step4-main" / "results"
PHASE2_DFT_DIR = REPO_ROOT / "experiments" / "phase2-main-dft"
PRED_DIR = PHASE2_DFT_DIR / "predictions"
MATERIALS_TOML = REPO_ROOT / "experiments" / "step4-main" / "materials" / "n10.toml"
FIXTURES_DIR = REPO_ROOT / "materials" / "fixtures"
REFERENCES_DIR = REPO_ROOT / "materials" / "references"


def load_materials() -> dict[str, dict]:
    with MATERIALS_TOML.open("rb") as f:
        return {m["slug"]: m for m in tomllib.load(f)["material"]}


def render_individual_prediction(
    cell_summary: dict,
    material: dict,
) -> dict:
    """個別 LLM 1 cell の prediction.json を生成 (Phase 1 ai-param-v1 互換)."""
    return {
        "material": f"{material['slug']}-{cell_summary['model_tag']}",
        "structure": material["structure_description"],
        "cif_fixture": f"materials/fixtures/{material['cif']}",
        "llm": {
            "model_id": cell_summary["model_id"],
            "model_tag": cell_summary["model_tag"],
            "model_family": cell_summary["model_family"],
            "model_size_B": cell_summary["model_size_B"],
            "is_reasoning": cell_summary["is_reasoning"],
            "source_experiment": "step4-main",
            "source_summary": str(
                Path("experiments/step4-main/results") /
                cell_summary["model_tag"] / material["slug"] / "summary.json"
            ),
            "n_trials": cell_summary["n_trials"],
            "n_valid": cell_summary["n_valid"],
            "unique_param_set_count": cell_summary["unique_param_set_count"],
            "fully_reproducible_params": cell_summary["fully_reproducible_params"],
            "rationale": "Mode params from N=10 trials in Step 4 main",
        },
        "params": cell_summary["mode_params"],
    }


def render_ensemble_prediction(
    ensemble_params: dict,
    material: dict,
    method: str,
) -> dict:
    """ensemble 1 cell の prediction.json (model_id 欄を ensemble 識別に使う)."""
    # _ で始まる meta key を params から外す
    clean_params = {
        k: v for k, v in ensemble_params.items() if not k.startswith("_")
    }
    return {
        "material": f"{material['slug']}-ensemble-{method}",
        "structure": material["structure_description"],
        "cif_fixture": f"materials/fixtures/{material['cif']}",
        "llm": {
            "model_id": f"ensemble-{method}",
            "ensemble_method": method,
            "n_contributing_LLMs": ensemble_params.get("_n_contributing", 0),
            "source_experiment": "step4-main",
            "rationale": f"Ensemble {method} computed post-hoc from 5-LLM mode params",
            "ensemble_metadata": {
                k: v for k, v in ensemble_params.items() if k.startswith("_")
            },
        },
        "params": clean_params,
    }


def is_insulator(formula: str, references_dir: Path) -> bool:
    """references/{formula}*.toml から is_insulator を読む."""
    for candidate in references_dir.glob(f"{formula}*.toml"):
        with candidate.open("rb") as f:
            d = tomllib.load(f)
        return bool(d.get("is_insulator", True))
    return True   # 不明なら絶縁体扱い (安全側)


def emit_individual_predictions(materials: dict[str, dict]) -> int:
    """Step 4 main 全 cell の summary.json を読み、prediction.json を出力."""
    cells = load_step4_summaries(STEP4_RESULTS)
    ok = 0
    for c in cells:
        material = materials.get(c.material_slug)
        if not material:
            print(f"  [skip] {c.model_tag}/{c.material_slug}: material not in n10.toml")
            continue
        if c.mode_params is None:
            print(f"  [skip] {c.model_tag}/{c.material_slug}: no mode_params (all trials invalid)")
            continue
        pred = render_individual_prediction(c.__dict__, material)
        out_name = f"{c.material_slug}-{c.model_tag}.json"
        out_path = PRED_DIR / out_name
        out_path.write_text(json.dumps(pred, indent=2, sort_keys=True))
        ok += 1
        print(f"  [ok ] {out_name}")
    return ok


def emit_ensemble_predictions(materials: dict[str, dict]) -> int:
    """ensemble 4 手法 × 10 材料の prediction.json を出力."""
    cells = load_step4_summaries(STEP4_RESULTS)
    if not cells:
        print("  no cells found")
        return 0

    # accuracy_weights: Phase 1 SUMMARY.md ベースの暫定値
    # Phase 2 完了後に Phase 2 自身のデータから再計算する想定
    accuracy_weights = {
        "qwen25-7b":   0.05,   # Phase 1 で完全失格
        "llama31-8b":  0.10,   # Phase 1 で convergence FAIL
        "llama33-70b": 0.30,   # Phase 1 で実用基準合格
        "gptoss-120b": 0.30,   # Phase 1 で完全合格
        "qwen3-32b":   0.25,   # Phase 1 で完全合格 (ref と同値だが weight 抑え目)
    }
    # MoE: Tier 別最良モデル (Phase 1 知見)
    tier_best = {
        "A": "gptoss-120b",
        "B": "qwen3-32b",
        "C": "llama33-70b",
    }
    # 材料 → insulator/metal
    insulator_map = {
        m["formula"]: is_insulator(m["formula"], REFERENCES_DIR)
        for m in materials.values()
    }

    reports = build_reports(cells, accuracy_weights, insulator_map, tier_best)
    ok = 0
    for r in reports:
        material = materials[r.material_slug]
        for method, ens in [("A", r.ensemble_A), ("B", r.ensemble_B),
                            ("C", r.ensemble_C), ("E", r.ensemble_E)]:
            if ens is None or ens.get("_failure"):
                print(f"  [skip] {r.material_slug}-ensemble-{method}: {ens.get('_failure') if ens else 'no result'}")
                continue
            pred = render_ensemble_prediction(ens, material, method)
            out_name = f"{r.material_slug}-ensemble-{method}.json"
            out_path = PRED_DIR / out_name
            out_path.write_text(json.dumps(pred, indent=2, sort_keys=True))
            ok += 1
            print(f"  [ok ] {out_name}")
    return ok


def trigger_workflow(experiment: str, formulas: list[str] | None = None) -> int:
    """gh workflow run ai-param-experiment.yml --field experiment=... ."""
    formulas_arg = ",".join(formulas) if formulas else ""
    cmd = [
        "gh", "workflow", "run", "ai-param-experiment.yml",
        "--field", f"experiment={experiment}",
        "--field", f"formulas={formulas_arg}",
    ]
    print(f"  $ {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
    return r.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-only", action="store_true",
                    help="JSON 生成のみ、push/trigger しない")
    ap.add_argument("--include-ensemble", action="store_true", default=True,
                    help="ensemble 結果も含める (default: True)")
    ap.add_argument("--no-ensemble", dest="include_ensemble", action="store_false")
    ap.add_argument("--trigger", action="store_true",
                    help="git add/commit/push してから gh workflow run")
    args = ap.parse_args()

    materials = load_materials()
    PRED_DIR.mkdir(parents=True, exist_ok=True)

    print("== Phase 2 Main DFT — emit individual LLM predictions ==")
    n_ind = emit_individual_predictions(materials)
    print(f"  → {n_ind} individual prediction.json")

    n_ens = 0
    if args.include_ensemble:
        print("\n== Phase 2 Main DFT — emit ensemble predictions ==")
        n_ens = emit_ensemble_predictions(materials)
        print(f"  → {n_ens} ensemble prediction.json")

    print(f"\nTotal: {n_ind} individual + {n_ens} ensemble = {n_ind + n_ens} cells")
    print(f"Output: {PRED_DIR}")

    if args.trigger:
        print("\n== git push + workflow trigger ==")
        # commit
        subprocess.run(["git", "add", str(PRED_DIR)], cwd=str(REPO_ROOT))
        subprocess.run([
            "git", "commit", "-m",
            f"phase2-main-dft: {n_ind + n_ens} predictions for ai-param-experiment workflow",
        ], cwd=str(REPO_ROOT))
        subprocess.run(["git", "push"], cwd=str(REPO_ROOT))
        print("\n  triggering ai-param-experiment.yml...")
        rc = trigger_workflow("phase2-main-dft")
        return rc

    print("\n(emit-only mode; rerun with --trigger to git push + gh workflow run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
