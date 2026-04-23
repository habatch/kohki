"""Aggregate downloaded ai-param-v1 artifacts into results/.

Usage:
    python3 aggregate.py <artifacts_root>

``artifacts_root`` is the directory where
``gh run download <RUN_ID> -D <artifacts_root>`` extracted the artifacts.
Each artifact subfolder looks like ``ai-param-{formula}/`` and contains
``{formula}.zip`` and ``{formula}.summary.json``.

Produces, under experiments/ai-param-v1/results/:
  - One merged ``summary.jsonl`` (one record per material)
  - One human-readable ``summary.md`` with the cross-material comparison
  - Copies of each material's provenance zip (for git commit)
"""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

EXP_ROOT = Path(__file__).resolve().parent
RESULTS = EXP_ROOT / "results"


def main(artifacts_root: Path) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []

    for summary_path in sorted(artifacts_root.rglob("*.summary.json")):
        record = json.loads(summary_path.read_text())
        formula = record["material"]
        # Copy the zip bundle in
        zip_src = summary_path.parent / f"{formula}.zip"
        if zip_src.exists():
            shutil.copy(zip_src, RESULTS / f"{formula}.zip")
        records.append(record)

    # summary.jsonl (mechanical consumption)
    jsonl = RESULTS / "summary.jsonl"
    with jsonl.open("w") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True) + "\n")

    # summary.md (human)
    md = ["# ai-param-v1 — cross-material summary", ""]
    md.append(f"Materials: **{len(records)}**, all using LLM-chosen pw.x params.")
    md.append("")
    md.append("| material | converged | SCF iter | ecutwfc / ecutrho Ry | k-points | conv_thr | mixing β | E_total Ry | Fermi eV | gap eV | wall s |")
    md.append("|----------|:---------:|:--------:|:-------------------:|:--------:|:--------:|:--------:|-----------:|---------:|-------:|-------:|")
    for r in sorted(records, key=lambda x: x["material"]):
        p = r["params"]
        fmt = lambda v: "-" if v is None else (f"{v:.6g}" if isinstance(v, float) else str(v))
        md.append("| {mat} | {conv} | {iter} | {ecw}/{ecr} | {k} | {ct:g} | {mb:.2f} | {E} | {F} | {g} | {w} |".format(
            mat=r["material"],
            conv="✓" if r["converged"] else "✗",
            iter=fmt(r["n_scf_iter"]),
            ecw=fmt(p["ecutwfc"]), ecr=fmt(p["ecutrho"]),
            k=str(tuple(p["kpoints"])),
            ct=p["conv_thr"], mb=p["mixing_beta"],
            E=fmt(r["total_energy_Ry"]),
            F=fmt(r["fermi_energy_eV"]),
            g=fmt(r["band_gap_eV"]),
            w=fmt(r["wall_seconds"]),
        ))
    md.append("")
    md.append(f"**LLM model**: `{records[0]['llm_model_id']}` (same for all rows)")
    md.append("")
    md.append("Every value above is reproducible from the per-material bundle "
              "(`{formula}.zip`) via `python3 -m orchestrator parse`.")

    (RESULTS / "summary.md").write_text("\n".join(md))

    print(f"wrote {jsonl}")
    print(f"wrote {RESULTS / 'summary.md'}")
    print(f"wrote {len(records)} bundle copies under {RESULTS}/")
    return 0


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ai-param-v1-artifacts")
    raise SystemExit(main(root))
