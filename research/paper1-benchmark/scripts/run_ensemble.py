"""Track A Phase 2 — Ensemble post-hoc CLI.

orchestrator/ensemble.py の薄い CLI ラッパー。
Step 4 main 結果を読んで 4 ensemble × 10 材料 の合成 params を表示 / 保存する。

使い方:
    python3 scripts/run_ensemble.py                       # コンソール表示
    python3 scripts/run_ensemble.py --json out.json       # JSON 保存
    python3 scripts/run_ensemble.py --md out.md           # markdown 表
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from orchestrator.ensemble import load_step4_summaries, build_reports

STEP4_RESULTS = REPO_ROOT / "experiments" / "step4-main" / "results"
REFERENCES_DIR = REPO_ROOT / "materials" / "references"


def load_insulator_map() -> dict[str, bool]:
    """references/{formula}*.toml から is_insulator マップを構築."""
    out: dict[str, bool] = {}
    for p in REFERENCES_DIR.glob("*.toml"):
        try:
            with p.open("rb") as f:
                d = tomllib.load(f)
            out[d["formula"]] = bool(d.get("is_insulator", True))
        except Exception:
            pass
    return out


# Phase 1 の知見から事前固定。Phase 2 完了後に Phase 2 自身のデータで再計算。
ACCURACY_WEIGHTS = {
    "qwen25-7b":   0.05,
    "llama31-8b":  0.10,
    "llama33-70b": 0.30,
    "gptoss-120b": 0.30,
    "qwen3-32b":   0.25,
}
TIER_BEST_MODEL = {
    "A": "gptoss-120b",
    "B": "qwen3-32b",
    "C": "llama33-70b",
}


def render_md_table(reports) -> str:
    lines = [
        "# Ensemble post-hoc results (Phase 2)",
        "",
        "| 材料 | Tier | A voting | B weighted | C guardrail | E moe | 一致度 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        a = _short(r.ensemble_A)
        b = _short(r.ensemble_B)
        c = _short(r.ensemble_C)
        e = _short(r.ensemble_E)
        lines.append(
            f"| {r.material_formula} | {r.material_tier} | {a} | {b} | {c} | {e} | "
            f"{r.cross_method_agreement*100:.0f}% |"
        )
    return "\n".join(lines) + "\n"


def _short(ens: dict | None) -> str:
    if ens is None or ens.get("_failure"):
        return f"FAIL ({ens.get('_failure', 'no result') if ens else 'none'})"
    ec = ens.get("ecutwfc", "?")
    sm = ens.get("smearing", "?")
    kp = ens.get("kpoints", "?")
    return f"ec={ec}/k={kp}/{sm}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="output JSON file")
    ap.add_argument("--md",   help="output markdown table file")
    ap.add_argument("--quiet", action="store_true", help="suppress console output")
    args = ap.parse_args()

    cells = load_step4_summaries(STEP4_RESULTS)
    if not cells:
        print(f"No Step 4 main summaries found under {STEP4_RESULTS}", file=sys.stderr)
        return 1

    insulator_map = load_insulator_map()
    reports = build_reports(cells, ACCURACY_WEIGHTS, insulator_map, TIER_BEST_MODEL)

    if not args.quiet:
        print(f"== Ensemble post-hoc ({len(reports)} materials, {len(cells)} input cells) ==\n")
        print(render_md_table(reports))

    if args.json:
        Path(args.json).write_text(
            json.dumps([r.to_dict() for r in reports], indent=2, sort_keys=True, default=str)
        )
        print(f"\nJSON written to {args.json}")

    if args.md:
        Path(args.md).write_text(render_md_table(reports))
        print(f"\nMarkdown written to {args.md}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
