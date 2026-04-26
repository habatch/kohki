"""Track A Phase 2 — Materials Project から不足 CIF を一括取得.

N=10 計画材料のうち materials/fixtures/ にまだ無いものを MP API から
ダウンロードし、(formula).cif で保存する。

使い方:
    source ~/.config/paper1/mp.env
    python3 scripts/fetch_mp_cifs.py
    python3 scripts/fetch_mp_cifs.py --formulas AlN,ZnO   # 特定材料のみ
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from orchestrator.materials import load_tier
from orchestrator.mp_client import MPClient

FIXTURE_DIR = REPO_ROOT / "materials" / "fixtures"


def safe_filename(formula: str, structure: str) -> str:
    keys = ("anatase", "rutile", "wurtzite", "zincblende", "hexagonal",
            "diamond", "perovskite", "monolayer")
    for k in keys:
        if k in structure.lower() and k not in formula.lower():
            return f"{formula}_{k}"
    return formula


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--formulas", help="comma-separated formula filter")
    ap.add_argument("--rate-sleep", type=float, default=0.5)
    ap.add_argument("--force", action="store_true",
                    help="re-download even if fixture exists")
    args = ap.parse_args()

    formulas = [f.strip() for f in args.formulas.split(",")] if args.formulas else None
    targets = []
    for tier in ("A", "B"):
        for m in load_tier(tier):
            if formulas and m.formula not in formulas:
                continue
            if not m.mp_id:
                continue
            targets.append(m)

    print(f"== fetch_mp_cifs == ({len(targets)} materials)")

    try:
        client = MPClient()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    skipped = 0
    failed: list[str] = []

    for m in targets:
        # まず短い formula 名 / polymorph 付き名 / formula 単独 の優先順で fixture
        # を探し、どれかあれば skip。
        candidates = [
            FIXTURE_DIR / f"{m.formula}.cif",
            FIXTURE_DIR / f"{safe_filename(m.formula, m.structure)}.cif",
        ]
        existing = [p for p in candidates if p.exists()]
        if existing and not args.force:
            print(f"  [skip] {m.formula:18}  exists ({existing[0].name})")
            skipped += 1
            continue

        out_path = FIXTURE_DIR / f"{safe_filename(m.formula, m.structure)}.cif"
        try:
            cif = client.cif(m.mp_id)
            out_path.write_text(cif)
            print(f"  [get ] {m.formula:18}  {m.mp_id:15}  →  {out_path.name}")
            ok += 1
        except Exception as e:
            print(f"  [FAIL] {m.formula:18}  {m.mp_id}  {e}")
            failed.append(m.formula)
        time.sleep(args.rate_sleep)

    print(f"\nDone: ok={ok} skipped={skipped} failed={len(failed)}")
    if failed:
        print("Failed:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
