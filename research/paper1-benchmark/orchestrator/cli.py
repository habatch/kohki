"""Paper 1 orchestrator CLI.

Subcommands::

    python3 -m orchestrator list-materials [--tier A|B|C|all]
    python3 -m orchestrator mp-fetch <mp_id> [--save-cif <path>]
    python3 -m orchestrator mp-sync [--tier A]          # fetch CIFs + GT for a tier
    python3 -m orchestrator pilot --material Si --backend local
    python3 -m orchestrator provenance show <bundle.zip>

Everything writes into ``results/`` so nothing leaks into git unless the
user commits it intentionally.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from orchestrator import materials as mat_mod
from orchestrator import provenance as prov


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"


def cmd_list_materials(args: argparse.Namespace) -> int:
    tiers = [args.tier] if args.tier != "all" else ["A", "B", "C"]
    for t in tiers:
        try:
            mats = mat_mod.load_tier(t)
        except FileNotFoundError:
            print(f"(tier {t}: no list yet)", file=sys.stderr)
            continue
        print(f"# Tier {t} — {len(mats)} materials")
        for m in mats:
            mp = f" [{m.mp_id}]" if m.mp_id else ""
            print(f"  {m.formula:<10} {m.structure:<16}{mp}")
    return 0


def cmd_mp_fetch(args: argparse.Namespace) -> int:
    from orchestrator.mp_client import MPClient
    client = MPClient()
    summ = client.summary(args.mp_id)
    print(json.dumps(
        {
            "material_id": summ.material_id,
            "formula": summ.formula_pretty,
            "band_gap_eV": summ.band_gap,
            "formation_energy_per_atom_eV": summ.formation_energy_per_atom,
            "is_gap_direct": summ.is_gap_direct,
            "is_metal": summ.is_metal,
            "volume_A3": summ.volume,
            "density_g_cm3": summ.density,
            "symmetry": summ.symmetry,
        },
        indent=2,
    ))
    if args.save_cif:
        cif = client.cif(args.mp_id)
        Path(args.save_cif).write_text(cif)
        print(f"CIF written to {args.save_cif}", file=sys.stderr)
    return 0


def cmd_mp_sync(args: argparse.Namespace) -> int:
    from orchestrator.mp_client import MPClient
    client = MPClient()
    mats = mat_mod.load_tier(args.tier)
    out_dir = RESULTS_DIR / "ground_truth" / f"tier_{args.tier.lower()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "mp_summary.jsonl"
    with prov.JsonlLog(log_path) as log:
        for m in mats:
            if not m.mp_id:
                print(f"[skip] {m.formula}: no mp_id", file=sys.stderr)
                continue
            try:
                summ = client.summary(m.mp_id)
            except Exception as e:
                print(f"[fail] {m.formula} ({m.mp_id}): {e}", file=sys.stderr)
                continue
            record = {
                "kind": "mp_summary",
                "formula": m.formula,
                "structure": m.structure,
                "tier": m.tier,
                "material_id": summ.material_id,
                "band_gap": summ.band_gap,
                "formation_energy_per_atom": summ.formation_energy_per_atom,
                "is_gap_direct": summ.is_gap_direct,
                "is_metal": summ.is_metal,
                "volume": summ.volume,
                "density": summ.density,
                "symmetry": summ.symmetry,
            }
            log.write(record)
            print(f"[ok]   {m.formula:<10} {summ.material_id:<10} "
                  f"gap={summ.band_gap}  ΔEf={summ.formation_energy_per_atom}")
            if args.save_cifs:
                cif = client.cif(m.mp_id)
                cif_path = out_dir / f"{m.formula}.cif"
                cif_path.write_text(cif)
    print(f"wrote {log_path}")
    return 0


def cmd_pilot(args: argparse.Namespace) -> int:
    # Minimal pilot: fetch one material's MP data, write the QE input
    # template, and log a fake DFTEvent so the provenance plumbing is
    # exercised end-to-end. No QE binary is invoked here — that happens
    # when dispatched to a backend.
    from orchestrator.mp_client import MPClient
    from orchestrator.qe_inputs import suggest_config, build_scf_input

    # Resolve material from any tier
    target = None
    for t in ("A", "B", "C"):
        try:
            for m in mat_mod.load_tier(t):
                if m.formula == args.material:
                    target = m
                    break
        except FileNotFoundError:
            continue
        if target:
            break
    if not target:
        print(f"Unknown material: {args.material}", file=sys.stderr)
        return 2

    out_dir = RESULTS_DIR / "pilot" / args.backend
    out_dir.mkdir(parents=True, exist_ok=True)

    elements = _guess_elements(target.formula)
    cfg = suggest_config(elements, likely_metal=False)
    qe_in = build_scf_input(target, cif_path=f"{target.formula}.cif", cfg=cfg)
    (out_dir / f"{target.formula}.in.template").write_text(qe_in)

    mp_summary = None
    if target.mp_id and os.environ.get("MP_API_KEY"):
        try:
            mp_summary = MPClient().summary(target.mp_id)
        except Exception as e:
            print(f"MP lookup failed: {e}", file=sys.stderr)

    pilot_record = {
        "kind": "pilot",
        "material": target.formula,
        "backend": args.backend,
        "mp_lookup": mp_summary.__dict__ if mp_summary else None,
        "input_template_sha": prov.sha256_text(qe_in),
    }
    with prov.JsonlLog(out_dir / "pilot.jsonl") as log:
        log.write(pilot_record)

    print(f"pilot scaffold ready at {out_dir}")
    print(f"  template : {target.formula}.in.template  "
          f"(sha={pilot_record['input_template_sha'][:12]})")
    if mp_summary:
        print(f"  MP gap   : {mp_summary.band_gap} eV  "
              f"direct={mp_summary.is_gap_direct}")
    return 0


def cmd_provenance_show(args: argparse.Namespace) -> int:
    import zipfile
    with zipfile.ZipFile(args.bundle) as z:
        try:
            meta = json.loads(z.read("metadata.json"))
        except KeyError:
            print("no metadata.json in bundle", file=sys.stderr)
            return 2
        print(json.dumps(meta, indent=2, sort_keys=True))
    return 0


def _guess_elements(formula: str) -> list[str]:
    """Return element symbols from a pretty formula like 'GaAs' or 'Cs2PbI4'."""
    import re
    return re.findall(r"[A-Z][a-z]?", formula)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="orchestrator")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list-materials")
    s.add_argument("--tier", choices=["A", "B", "C", "all"], default="all")
    s.set_defaults(func=cmd_list_materials)

    s = sub.add_parser("mp-fetch")
    s.add_argument("mp_id")
    s.add_argument("--save-cif")
    s.set_defaults(func=cmd_mp_fetch)

    s = sub.add_parser("mp-sync")
    s.add_argument("--tier", default="A")
    s.add_argument("--save-cifs", action="store_true")
    s.set_defaults(func=cmd_mp_sync)

    s = sub.add_parser("pilot")
    s.add_argument("--material", required=True)
    s.add_argument("--backend", default="local",
                   choices=["local", "github", "kaggle", "oracle", "gcp", "aws"])
    s.set_defaults(func=cmd_pilot)

    s = sub.add_parser("provenance")
    s2 = s.add_subparsers(dest="prov_cmd", required=True)
    sh = s2.add_parser("show")
    sh.add_argument("bundle")
    sh.set_defaults(func=cmd_provenance_show)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
