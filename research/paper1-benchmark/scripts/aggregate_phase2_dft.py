"""Track A Phase 2 — DFT 結果集計 (Phase 2 main + ensemble + reference).

GitHub Actions の ai-param-experiment workflow の artifact (bundle zip) を
ダウンロード/展開し、pw.x output.out を qe_parser でパース、accuracy_metrics
で 5 指標スコアを付け、最終的に SUMMARY.md と JSON 表を生成する。

入力前提:
  - gh CLI 認証済 (gh auth status)
  - Actions の以下 run が完了していること:
      ai-param-experiment.yml  experiment=phase2-main-dft  (89 cells)
      ai-param-experiment.yml  experiment=ref-convergence  (50 cells)

使い方:
  python3 scripts/aggregate_phase2_dft.py --download   # artifact 取得 + 展開
  python3 scripts/aggregate_phase2_dft.py --aggregate  # 既存 bundle を集計のみ
  python3 scripts/aggregate_phase2_dft.py --all        # 上記両方

出力:
  experiments/phase2-main-dft/results/   (artifacts 展開先)
  experiments/phase2-main-dft/results/SUMMARY.md
  experiments/phase2-main-dft/results/accuracy_table.json
  experiments/ref-convergence/results/   (ref artifacts 展開先)
  experiments/ref-convergence/results/convergence_curves.json
  materials/references/{formula}*.toml に e_total_converged_Ry_per_atom 自動追記
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from orchestrator.qe_parser import parse_pw_file
from orchestrator.accuracy_metrics import (
    score_cell, MaterialReference, MetricStatus, aggregate_by_model, aggregate_by_material,
    load_reference_toml, evaluate_convergence,
)

PHASE2_DFT_DIR = REPO_ROOT / "experiments" / "phase2-main-dft"
PHASE2_RESULTS = PHASE2_DFT_DIR / "results"
REF_DIR = REPO_ROOT / "experiments" / "ref-convergence"
REF_RESULTS = REF_DIR / "results"
REFERENCES_DIR = REPO_ROOT / "materials" / "references"
MATERIALS_TOML = REPO_ROOT / "experiments" / "step4-main" / "materials" / "n10.toml"


# ---------------------------------------------------------------------------
# GH Actions artifact ダウンロード
# ---------------------------------------------------------------------------

def download_artifacts(experiment: str, dest: Path) -> int:
    """gh CLI で最新 successful run の artifacts を取得."""
    dest.mkdir(parents=True, exist_ok=True)
    print(f"== Downloading artifacts for experiment={experiment} → {dest} ==")
    # 最新 run id を取得 (workflow=ai-param-experiment.yml で experiment 一致)
    cmd = [
        "gh", "run", "list",
        "--workflow", "ai-param-experiment.yml",
        "--limit", "20",
        "--json", "databaseId,displayTitle,status,conclusion,createdAt",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr); return 0
    runs = json.loads(r.stdout)
    # 最新 completed/success run を選ぶ (experiment 文字列で粗く識別、
    # gh では input 値はそのまま title に出ないので最新成功を取る)
    successful = [
        x for x in runs
        if x["status"] == "completed" and x["conclusion"] == "success"
    ]
    if not successful:
        print(f"  no completed/successful runs found", file=sys.stderr)
        return 0
    run_id = successful[0]["databaseId"]
    print(f"  using run {run_id} ({successful[0]['createdAt']})")

    cmd = ["gh", "run", "download", str(run_id), "--dir", str(dest)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr); return 0

    # artifacts は dest/ 配下にディレクトリで展開される
    n_zips = len(list(dest.rglob("*.zip")))
    n_outputs = len(list(dest.rglob("output.out")))
    print(f"  downloaded: {n_zips} zips, {n_outputs} output.out files")
    return n_outputs


# ---------------------------------------------------------------------------
# Phase 2 main DFT 集計
# ---------------------------------------------------------------------------

def parse_cell_name(material_field: str) -> tuple[str, str]:
    """prediction.json の "material" フィールドから (material_slug, model_or_ensemble_tag).

    例: "Si-llama33-70b" → ("Si", "llama33-70b")
        "CsPbI3-ensemble-C" → ("CsPbI3", "ensemble-C")
    """
    parts = material_field.split("-", 1)
    if len(parts) != 2:
        return material_field, "?"
    return parts[0], parts[1]


def load_material_specs() -> dict[str, dict]:
    with MATERIALS_TOML.open("rb") as f:
        return {m["slug"]: m for m in tomllib.load(f)["material"]}


def build_reference_map(materials: dict[str, dict]) -> dict[str, MaterialReference]:
    """各材料の MaterialReference を materials/references/ から読み込む."""
    out: dict[str, MaterialReference] = {}
    for slug, m in materials.items():
        formula = m["formula"]
        # references/{formula}*.toml を試す
        for candidate in REFERENCES_DIR.glob(f"{formula}*.toml"):
            try:
                ref = load_reference_toml(candidate)
                out[slug] = ref
                break
            except Exception as e:
                print(f"  WARN: {candidate}: {e}")
    return out


def find_bundle_dirs(results_dir: Path) -> list[Path]:
    """download 後の results/ 直下にある artifact ディレクトリを列挙."""
    if not results_dir.exists():
        return []
    out = []
    for child in results_dir.iterdir():
        if child.is_dir() and (child / "output.out").exists():
            out.append(child)
        elif child.is_dir():
            # subdirectory を 1 階層下まで掘る
            for sub in child.iterdir():
                if sub.is_dir() and (sub / "output.out").exists():
                    out.append(sub)
    return out


def aggregate_phase2_main() -> int:
    materials = load_material_specs()
    ref_map = build_reference_map(materials)
    bundles = find_bundle_dirs(PHASE2_RESULTS)
    print(f"Found {len(bundles)} bundles in {PHASE2_RESULTS}")

    # 期待される全 cell 一覧 (predictions/ から) を取得し、artifact が欠落した
    # cell を「DFT failed before artifact upload」として記録する。
    expected_cells: set[str] = set()
    pred_dir = PHASE2_DFT_DIR / "predictions"
    if pred_dir.exists():
        expected_cells = {p.stem for p in pred_dir.glob("*.json")}
    found_cells: set[str] = set()

    rows: list[dict[str, Any]] = []
    for bundle in bundles:
        try:
            pred = json.loads((bundle / "prediction.json").read_text())
        except FileNotFoundError:
            print(f"  [skip] {bundle.name}: no prediction.json")
            continue
        material_field = pred.get("material", bundle.name)
        found_cells.add(material_field)
        slug, tag = parse_cell_name(material_field)
        ref = ref_map.get(slug)
        if not ref:
            print(f"  [warn] {material_field}: no reference (skip metrics)")
            continue
        try:
            obs = parse_pw_file(bundle / "output.out")
        except Exception as e:
            print(f"  [fail] {material_field}: parse error {e}")
            continue

        proposed_smearing = pred["params"].get("smearing")
        proposed_degauss = float(pred["params"].get("degauss", 0))

        score = score_cell(
            model=tag,
            obs=obs,
            ref=ref,
            proposed_smearing=proposed_smearing,
            proposed_degauss_Ry=proposed_degauss,
        )
        rows.append({
            "material_slug": slug,
            "tag": tag,                # model_tag or ensemble-{X}
            "is_ensemble": tag.startswith("ensemble-"),
            "wall_seconds": obs.wall_seconds,
            "total_energy_Ry": obs.total_energy_Ry,
            "fermi_eV": obs.fermi_energy_eV,
            "converged": obs.converged,
            "n_scf_iter": obs.n_scf_iter,
            "scores": {
                "convergence": score.convergence.to_dict(),
                "smearing_validity": score.smearing_validity.to_dict(),
                "band_gap_validity": score.band_gap_validity.to_dict(),
                "cost_efficiency": score.cost_efficiency.to_dict(),
                "overall": score.overall_status().value,
                "n_pass": score.n_pass(),
                "n_fail": score.n_fail(),
            },
        })

    # artifact 欠落 cell を「dft_failed_no_artifact」として記録
    missing = expected_cells - found_cells
    for cell in sorted(missing):
        slug, tag = parse_cell_name(cell)
        rows.append({
            "material_slug": slug,
            "tag": tag,
            "is_ensemble": tag.startswith("ensemble-"),
            "wall_seconds": None,
            "total_energy_Ry": None,
            "fermi_eV": None,
            "converged": False,
            "n_scf_iter": None,
            "scores": {
                "convergence": {
                    "name": "convergence",
                    "status": "unphysical",
                    "value": None,
                    "threshold": None,
                    "reason": "no artifact uploaded — DFT likely failed before bundle (probable pre-SCF rejection)",
                    "extra": {"no_artifact": True},
                },
                "smearing_validity": {"status": "unknown"},
                "band_gap_validity": {"status": "unknown"},
                "cost_efficiency": {"status": "unknown"},
                "overall": "unphysical",
                "n_pass": 0,
                "n_fail": 0,
                "n_unphysical": 1,
                "no_artifact": True,
            },
        })
    if missing:
        print(f"  WARN: {len(missing)} cells without artifact (recorded as unphysical)")

    PHASE2_RESULTS.mkdir(parents=True, exist_ok=True)
    table_path = PHASE2_RESULTS / "accuracy_table.json"
    table_path.write_text(json.dumps(rows, indent=2, sort_keys=True, default=str))
    print(f"  → {table_path} ({len(rows)} rows)")

    # SUMMARY.md
    md = render_summary_md(rows, materials, ref_map)
    md_path = PHASE2_RESULTS / "SUMMARY.md"
    md_path.write_text(md)
    print(f"  → {md_path}")
    return len(rows)


def render_summary_md(rows: list[dict], materials: dict, ref_map: dict) -> str:
    lines = [
        "# Phase 2 Main DFT — accuracy summary (auto-generated)",
        "",
        "## 7 LLM × 10 materials + 4 ensemble methods",
        "",
        "### 個別 LLM cells",
        "",
        "| material | model_tag | overall | conv (mRy/atom) | smearing | E_total Ry | wall s |",
        "|---|---|---|---|---|---|---|",
    ]
    indiv = [r for r in rows if not r["is_ensemble"]]
    ens = [r for r in rows if r["is_ensemble"]]
    for r in sorted(indiv, key=lambda x: (x["material_slug"], x["tag"])):
        sc = r["scores"]
        conv_v = sc["convergence"].get("value")
        conv_str = f"{conv_v:.2f}" if conv_v is not None else "n/a"
        sm_str = sc["smearing_validity"]["status"]
        e = r["total_energy_Ry"]
        e_str = f"{e:.4f}" if e is not None else "n/a"
        w = r["wall_seconds"]
        w_str = f"{w:.0f}" if w is not None else "n/a"
        lines.append(
            f"| {r['material_slug']} | {r['tag']} | {sc['overall']} | {conv_str} | {sm_str} | {e_str} | {w_str} |"
        )
    lines.append("")
    lines.append("### Ensemble cells")
    lines.append("")
    lines.append("| material | ensemble | overall | conv (mRy/atom) | smearing | E_total Ry | wall s |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in sorted(ens, key=lambda x: (x["material_slug"], x["tag"])):
        sc = r["scores"]
        conv_v = sc["convergence"].get("value")
        conv_str = f"{conv_v:.2f}" if conv_v is not None else "n/a"
        sm_str = sc["smearing_validity"]["status"]
        e = r["total_energy_Ry"]
        e_str = f"{e:.4f}" if e is not None else "n/a"
        w = r["wall_seconds"]
        w_str = f"{w:.0f}" if w is not None else "n/a"
        lines.append(
            f"| {r['material_slug']} | {r['tag']} | {sc['overall']} | {conv_str} | {sm_str} | {e_str} | {w_str} |"
        )
    lines.append("")

    # アグリゲート (model 別)
    by_model: dict[str, list] = defaultdict(list)
    for r in indiv:
        by_model[r["tag"]].append(r)
    lines += [
        "## Per-model aggregate (個別 LLM のみ)",
        "",
        "| model_tag | n_cells | pass | fail | **unphysical** | conv_pass | smearing_pass | wall mean s |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for tag, group in sorted(by_model.items()):
        n = len(group)
        n_pass = sum(1 for r in group if r["scores"]["overall"] == "pass")
        n_fail = sum(1 for r in group if r["scores"]["overall"] == "fail")
        n_unphysical = sum(1 for r in group if r["scores"]["overall"] == "unphysical")
        n_conv_pass = sum(1 for r in group if r["scores"]["convergence"]["status"] == "pass")
        n_sm_pass = sum(1 for r in group if r["scores"].get("smearing_validity", {}).get("status") == "pass")
        walls = [r["wall_seconds"] for r in group if r["wall_seconds"]]
        wmean = sum(walls) / len(walls) if walls else 0
        lines.append(
            f"| {tag} | {n} | {n_pass}/{n} ({n_pass/n*100:.0f}%) | {n_fail}/{n} | "
            f"**{n_unphysical}/{n}** | {n_conv_pass/n*100:.0f}% | {n_sm_pass/n*100:.0f}% | {wmean:.0f} |"
        )

    # 「unphysical」cell の詳細リスト (LLM の物理破綻パターン)
    unphysical_rows = [r for r in rows if r["scores"]["overall"] == "unphysical"]
    if unphysical_rows:
        lines += [
            "",
            "## ⚠ Unphysical proposals — LLM が物理的に成立しない params を提案",
            "",
            "| cell | reason |",
            "|---|---|",
        ]
        for r in sorted(unphysical_rows, key=lambda x: (x["material_slug"], x["tag"])):
            reason = r["scores"]["convergence"].get("reason", "(no reason)")
            lines.append(f"| {r['material_slug']}-{r['tag']} | {reason} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Reference convergence test 集計
# ---------------------------------------------------------------------------

REF_FILENAME_RE = re.compile(r"^(?P<slug>.+?)-ref-ecut(?P<ecut>\d+)$")


def aggregate_ref_convergence() -> int:
    """ecut sweep の結果から E_total vs ecut カーブを生成、収束値を抽出."""
    materials = load_material_specs()
    bundles = find_bundle_dirs(REF_RESULTS)
    print(f"Found {len(bundles)} ref bundles in {REF_RESULTS}")

    by_material: dict[str, list[tuple[int, float, int]]] = defaultdict(list)
    for bundle in bundles:
        try:
            pred = json.loads((bundle / "prediction.json").read_text())
        except FileNotFoundError:
            continue
        m = REF_FILENAME_RE.match(pred.get("material", bundle.name))
        if not m:
            continue
        slug = m.group("slug")
        ecut = int(m.group("ecut"))
        try:
            obs = parse_pw_file(bundle / "output.out")
        except Exception as e:
            print(f"  [fail] {bundle.name}: {e}")
            continue
        if obs.total_energy_Ry is None or obs.n_atoms is None:
            continue
        by_material[slug].append((ecut, obs.total_energy_Ry / obs.n_atoms, obs.n_atoms))

    REF_RESULTS.mkdir(parents=True, exist_ok=True)
    curves = {}
    for slug, points in by_material.items():
        points.sort()
        # 「収束値」: 最高 ecut の値 (sweep の高 ecut 端で平坦化していると仮定)
        e_per_atom_at_max = points[-1][1] if points else None
        # convergence indicator: 高 2 点の差 (mRy/atom)
        delta_mRy = None
        if len(points) >= 2:
            delta_mRy = abs(points[-1][1] - points[-2][1]) * 1000.0
        curves[slug] = {
            "ecut_points": [p[0] for p in points],
            "e_total_per_atom_Ry": [p[1] for p in points],
            "n_atoms": points[0][2] if points else None,
            "e_total_converged_Ry_per_atom_max_ecut": e_per_atom_at_max,
            "delta_at_top_mRy_per_atom": delta_mRy,
            "is_converged_estimate": (delta_mRy is not None and delta_mRy <= 1.0),
        }
        # references/{formula}*.toml に追記
        formula = materials.get(slug, {}).get("formula", slug)
        for cand in REFERENCES_DIR.glob(f"{formula}*.toml"):
            patch_reference_toml(cand, e_per_atom_at_max)
            break

    out_path = REF_RESULTS / "convergence_curves.json"
    out_path.write_text(json.dumps(curves, indent=2, sort_keys=True, default=str))
    print(f"  → {out_path} ({len(curves)} materials)")
    return len(curves)


def patch_reference_toml(path: Path, e_per_atom: float | None) -> None:
    """既存 toml に e_total_converged_Ry_per_atom 行を追記 (なければ作成)."""
    if e_per_atom is None:
        return
    text = path.read_text()
    new_line = f"e_total_converged_Ry_per_atom = {e_per_atom:.6f}\n"
    if "e_total_converged_Ry_per_atom" in text:
        text = re.sub(
            r"e_total_converged_Ry_per_atom\s*=\s*[\-\d\.e+]+",
            new_line.strip(),
            text,
        )
    else:
        text += "\n# auto-added by aggregate_phase2_dft.py from ecut sweep\n" + new_line
    path.write_text(text)
    print(f"  patched {path.name}: e_total_converged_Ry_per_atom = {e_per_atom:.6f}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true",
                    help="gh run download で artifact 取得")
    ap.add_argument("--aggregate", action="store_true",
                    help="既存 bundle を集計")
    ap.add_argument("--all", action="store_true",
                    help="--download + --aggregate 両方")
    ap.add_argument("--phase2-only", action="store_true",
                    help="phase2-main-dft のみ")
    ap.add_argument("--ref-only", action="store_true",
                    help="ref-convergence のみ")
    args = ap.parse_args()

    if args.all:
        args.download = True
        args.aggregate = True
    if not (args.download or args.aggregate):
        ap.print_help()
        return 1

    do_phase2 = not args.ref_only
    do_ref = not args.phase2_only

    if args.download:
        if do_phase2:
            download_artifacts("phase2-main-dft", PHASE2_RESULTS)
        if do_ref:
            download_artifacts("ref-convergence", REF_RESULTS)

    if args.aggregate:
        if do_ref:
            print("\n== Aggregate reference convergence ==")
            aggregate_ref_convergence()
        if do_phase2:
            print("\n== Aggregate Phase 2 main DFT ==")
            aggregate_phase2_main()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
