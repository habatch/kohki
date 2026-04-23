"""Generate doped Si supercells from Tier C recipes.

Uses ASE to build pristine Si, expand to the requested supercell, and
apply the recipe (substitutional / vacancy / interstitial / pristine).
The resulting CIF is written to ``materials/fixtures/<formula>.cif`` so
the GitHub Actions workflow picks it up via the same fixture path it
uses for Tier A/B.

This module does have one external dep — ASE — so call sites must run
under the ``qe`` conda env (or have ``ase`` installed otherwise). That's
why we keep it separate from the stdlib-only orchestrator core.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.materials import Material


TETRAHEDRAL_INTERSTITIAL = (0.5, 0.5, 0.5)  # fractional, for a Si T-site


def _parse_supercell(tag: str) -> tuple[int, int, int]:
    try:
        a, b, c = (int(x) for x in tag.split("x"))
    except ValueError as e:
        raise ValueError(f"bad supercell tag {tag!r}, expected NxMxK") from e
    return a, b, c


def generate_cif(mat: Material, out_dir: Path, a_ang: float = 5.43) -> Path:
    """Generate a CIF for a Tier C material. Returns the written path.

    Caller is expected to have validated that ``mat.tier == "C"`` and that
    ``mat.extra["recipe"]`` exists.
    """
    from ase.build import bulk
    from ase.io import write

    recipe = mat.extra.get("recipe")
    if not isinstance(recipe, dict):
        raise ValueError(f"{mat.formula}: recipe missing or not a table")

    kind = recipe.get("type")
    size = _parse_supercell(str(recipe.get("supercell", "2x2x2")))

    # Build pristine Si diamond conventional cell (8 atoms), then tile.
    si_prim = bulk("Si", "diamond", a=a_ang, cubic=True)
    cell = si_prim * size

    if kind == "pristine":
        pass

    elif kind == "substitutional":
        dopant = str(recipe["dopant"])
        idx = int(recipe.get("site_index", 0))
        if not (0 <= idx < len(cell)):
            raise ValueError(f"site_index {idx} out of range for {len(cell)}-atom cell")
        cell[idx].symbol = dopant

    elif kind == "vacancy":
        idx = int(recipe.get("site_index", 0))
        if not (0 <= idx < len(cell)):
            raise ValueError(f"site_index {idx} out of range for {len(cell)}-atom cell")
        del cell[idx]

    elif kind == "interstitial":
        from ase import Atom
        dopant = str(recipe["dopant"])
        frac = recipe.get("site_frac", TETRAHEDRAL_INTERSTITIAL)
        pos = cell.cell.cartesian_positions(frac)
        cell.append(Atom(dopant, position=pos))

    else:
        raise ValueError(f"unknown recipe.type={kind!r}")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{mat.formula}.cif"
    write(str(out_path), cell)
    return out_path


def main() -> int:
    """CLI: regenerate every Tier C fixture. Idempotent."""
    import sys
    from orchestrator.materials import load_tier
    from orchestrator.cli import REPO_ROOT

    out_dir = REPO_ROOT / "materials" / "fixtures"
    count = 0
    for mat in load_tier("C"):
        if "recipe" not in mat.extra:
            print(f"skip {mat.formula}: no recipe", file=sys.stderr)
            continue
        try:
            path = generate_cif(mat, out_dir)
            # Re-count atoms for sanity output
            from ase.io import read
            atoms = read(str(path))
            print(f"  {mat.formula:<10} {len(atoms):>3} atoms  →  {path.relative_to(REPO_ROOT)}")
            count += 1
        except Exception as e:
            print(f"  {mat.formula}: FAIL {e}", file=sys.stderr)
    print(f"generated {count} CIFs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
