"""Track A Phase 2 — Reference convergence test runner.

各材料で ecutwfc を [30, 40, 50, 60, 80] Ry の 5 点 sweep し、
E_total vs ecut カーブから「収束した参照値」を抽出する。
これは accuracy_metrics の e_total_converged_Ry_per_atom フィールドの真値となる。

実装方針:
  ai-param-experiment.yml workflow を流用する。
  各 ecut 点を 1 つの "prediction" として扱い、predictions/{material}-ref-ecutXXX.json
  を 5 個 × 10 材料 = 50 個生成する。
  workflow が pw.x で実行 → bundle 取得 → 結果から E_total vs ecut カーブ抽出。

入力:
    experiments/step4-main/materials/n10.toml  (10 材料の構造情報)
    materials/fixtures/{cif}                    (CIF)
    materials/pseudos/                          (pseudo)

出力:
    experiments/ref-convergence/predictions/{material}-ref-ecutXXX.json  (50 ファイル)

使い方:
    python3 scripts/run_ref_convergence.py --emit-only
    python3 scripts/run_ref_convergence.py --trigger      # git push + gh workflow run

ecut sweep 点:
    [30, 40, 50, 60, 80] Ry  (default)
    --ecut-points "30,40,50,60,80,100" でカスタム可
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MATERIALS_TOML = REPO_ROOT / "experiments" / "step4-main" / "materials" / "n10.toml"
REF_DIR = REPO_ROOT / "experiments" / "ref-convergence"
PRED_DIR = REF_DIR / "predictions"

DEFAULT_ECUT_POINTS = [30, 40, 50, 60, 80]
DEFAULT_KPOINTS = [4, 4, 4]      # reference には適度な k-density を固定
DEFAULT_SMEARING = "gaussian"
DEFAULT_DEGAUSS = 0.005          # 安全側の小 degauss
DEFAULT_CONV_THR = 1e-10
DEFAULT_MIXING_BETA = 0.4


def load_materials() -> list[dict]:
    with MATERIALS_TOML.open("rb") as f:
        return tomllib.load(f)["material"]


def k_density_for_material(material: dict) -> list[int]:
    """大型 cell では k 密度を下げる (n_atoms に応じて)."""
    n = material.get("n_atoms", 2)
    if n >= 64:
        return [2, 2, 2]   # supercell は k=2x2x2 でも十分
    if n >= 16:
        return [3, 3, 3]   # 中型 cell
    if "monolayer" in material.get("structure_description", "").lower():
        return [6, 6, 1]   # 2D は kz=1
    return DEFAULT_KPOINTS


def render_ref_prediction(material: dict, ecut: int, kpoints: list[int]) -> dict:
    """1 ecut 点の prediction.json (ai-param-experiment.yml 形式)."""
    return {
        "material": f"{material['slug']}-ref-ecut{ecut:03d}",
        "structure": material["structure_description"],
        "cif_fixture": f"materials/fixtures/{material['cif']}",
        "llm": {
            "model_id": f"reference-convergence-test-ecut{ecut}",
            "source_experiment": "ref-convergence",
            "rationale": f"Reference convergence sweep point: ecutwfc={ecut} Ry",
            "is_reference": True,
        },
        "params": {
            "ecutwfc": float(ecut),
            "ecutrho": float(ecut * 4),    # norm-conserving 最低比 4
            "kpoints": kpoints,
            "smearing": DEFAULT_SMEARING,
            "degauss": DEFAULT_DEGAUSS,
            "conv_thr": DEFAULT_CONV_THR,
            "mixing_beta": DEFAULT_MIXING_BETA,
        },
    }


def emit_predictions(ecut_points: list[int]) -> int:
    materials = load_materials()
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for material in materials:
        kp = k_density_for_material(material)
        for ecut in ecut_points:
            pred = render_ref_prediction(material, ecut, kp)
            out_name = f"{material['slug']}-ref-ecut{ecut:03d}.json"
            (PRED_DIR / out_name).write_text(json.dumps(pred, indent=2, sort_keys=True))
            ok += 1
            print(f"  [ok ] {out_name}  (k={kp})")
    return ok


def trigger_workflow() -> int:
    cmd = [
        "gh", "workflow", "run", "ai-param-experiment.yml",
        "--field", "experiment=ref-convergence",
        "--field", "formulas=",
    ]
    print(f"  $ {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
    return r.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ecut-points", default="30,40,50,60,80",
                    help="comma-separated ecutwfc Ry sweep points")
    ap.add_argument("--emit-only", action="store_true")
    ap.add_argument("--trigger", action="store_true")
    args = ap.parse_args()

    ecut_points = [int(x) for x in args.ecut_points.split(",")]

    print(f"== Reference convergence sweep ==")
    print(f"  ecut sweep points: {ecut_points} Ry")
    n = emit_predictions(ecut_points)
    print(f"\nTotal: {n} reference predictions emitted")

    if args.trigger:
        print("\n== git push + workflow trigger ==")
        subprocess.run(["git", "add", str(PRED_DIR)], cwd=str(REPO_ROOT))
        subprocess.run([
            "git", "commit", "-m",
            f"ref-convergence: {n} ecut sweep predictions for reference value extraction",
        ], cwd=str(REPO_ROOT))
        subprocess.run(["git", "push"], cwd=str(REPO_ROOT))
        rc = trigger_workflow()
        return rc

    print("\n(emit-only mode; rerun with --trigger to git push + gh workflow run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
