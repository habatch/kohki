"""Generate minimal QE pw.x input decks from a Material spec.

Keeps scope narrow: single-step SCF only (good for a pilot). The full
relax/NSCF/DOS/bands pipeline already exists in the qe-desktop app; we
reuse its Python helper when running on a backend that has it, and fall
back to this self-contained template when running in an isolated env
like GitHub Actions or a Kaggle notebook.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.materials import Material

# Pseudopotential defaults. The pilot assumes SSSP Efficiency bundled via
# the ``sssp`` conda-forge package which stages files at
# ``$PSEUDO_DIR/sssp_efficiency_pbe/{Element}.upf``.
SSSP_EFFICIENCY_CUTOFFS: dict[str, tuple[int, int]] = {
    # ecutwfc Ry, ecutrho Ry — pulled from the Materials Cloud
    # recommended set. Used when MP doesn't suggest something else.
    "H":  (80, 640),  "He": (55, 220), "Li": (40, 320), "Be": (50, 200),
    "B":  (40, 320),  "C":  (45, 360), "N":  (60, 480), "O":  (60, 480),
    "F":  (50, 200),  "Ne": (40, 200), "Na": (40, 320), "Mg": (30, 240),
    "Al": (30, 240),  "Si": (30, 240), "P":  (30, 240), "S":  (35, 280),
    "Cl": (50, 200),  "Ar": (60, 240), "K":  (45, 360), "Ca": (30, 240),
    "Sc": (40, 320),  "Ti": (45, 360), "V":  (40, 320), "Cr": (40, 320),
    "Mn": (65, 780),  "Fe": (90, 1080), "Co": (45, 540), "Ni": (45, 540),
    "Cu": (55, 660),  "Zn": (40, 320), "Ga": (55, 440), "Ge": (40, 320),
    "As": (35, 280),  "Se": (30, 240), "Br": (30, 240), "Rb": (30, 240),
    "Sr": (30, 240),  "Y":  (35, 280), "Zr": (30, 240), "Nb": (40, 320),
    "Mo": (35, 280),  "Ru": (35, 280), "Rh": (35, 280), "Pd": (45, 360),
    "Ag": (50, 400),  "Cd": (60, 480), "In": (50, 400), "Sn": (35, 280),
    "Sb": (40, 320),  "Te": (30, 240), "I":  (35, 280), "Xe": (60, 480),
    "Cs": (30, 240),  "Ba": (30, 240), "La": (40, 320), "Hf": (50, 400),
    "Ta": (45, 360),  "W":  (30, 240), "Re": (30, 240), "Os": (40, 320),
    "Ir": (50, 400),  "Pt": (35, 280), "Au": (45, 360), "Hg": (50, 400),
    "Tl": (50, 400),  "Pb": (40, 320), "Bi": (45, 360),
}


@dataclass
class QeConfig:
    ecutwfc: float                  # Ry
    ecutrho: float                  # Ry
    kpoints: tuple[int, int, int]
    smearing: str = "marzari-vanderbilt"
    degauss: float = 0.01
    conv_thr: float = 1.0e-8
    pseudo_dir: str = "./pseudo"
    outdir: str = "./tmp"


def suggest_config(
    elements: list[str],
    likely_metal: bool = False,
    *,
    n_atoms: int | None = None,
    cell_abc_ang: tuple[float, float, float] | None = None,
) -> QeConfig:
    """Suggest ecutwfc/ecutrho/kpoints given elements + cell context.

    k-grid scaling matters: a 2×2×2 supercell of Si has a Brillouin zone
    8× smaller than the primitive, so using the same 6×6×6 mesh is 8×
    wasted compute. We target a k-spacing of ~0.25 Å⁻¹ which is plenty
    for semiconductors, and floor at 2×2×2 so γ-only pitfalls (symmetry
    under-sampling) are avoided for non-tiny cells.
    """
    ecw = max(SSSP_EFFICIENCY_CUTOFFS.get(el, (40, 320))[0] for el in elements)
    ecr = max(SSSP_EFFICIENCY_CUTOFFS.get(el, (40, 320))[1] for el in elements)

    kpts = (6, 6, 6)  # default for primitive / unknown
    if cell_abc_ang is not None:
        # Target reciprocal-space density ~0.25 /Å, which maps to
        # n_k ≈ 2π / (a·0.25) = 25 / a for a in Å. Round up, floor to 2,
        # ceiling to 8 so we don't blow memory on huge cells.
        def pick(a: float) -> int:
            return max(2, min(8, int(25.0 / max(a, 1.0)) + 1))
        kpts = tuple(pick(a) for a in cell_abc_ang)  # type: ignore[assignment]

    return QeConfig(
        ecutwfc=float(ecw),
        ecutrho=float(ecr),
        kpoints=kpts,
        smearing=("marzari-vanderbilt" if likely_metal else "gaussian"),
    )


def build_scf_input(material: Material, cif_path: Path | str, cfg: QeConfig) -> str:
    """Return the text of an SCF ``pw.x`` input deck referencing ``cif_path``.

    Uses QE's ``ibrav = 0`` + CELL_PARAMETERS / ATOMIC_POSITIONS. Because
    we don't parse CIF here, we expect the backend to translate the CIF
    to explicit cell+atoms before invoking pw.x (ASE's ``ase.io.read`` +
    ``write(format='espresso-in')`` is the canonical way). This function
    emits the parameters block only; the backend appends the geometry.
    """
    ry_scale = "bohr"
    title = f"Paper1 {material.formula} ({material.structure}, tier {material.tier})"
    return f"""&CONTROL
  calculation   = 'scf'
  prefix        = '{material.formula}'
  pseudo_dir    = '{cfg.pseudo_dir}'
  outdir        = '{cfg.outdir}'
  verbosity     = 'high'
  tprnfor       = .true.
  tstress       = .true.
  title         = '{title}'
/
&SYSTEM
  ibrav         = 0
  nat           = @NAT@
  ntyp          = @NTYP@
  ecutwfc       = {cfg.ecutwfc}
  ecutrho       = {cfg.ecutrho}
  occupations   = 'smearing'
  smearing      = '{cfg.smearing}'
  degauss       = {cfg.degauss}
/
&ELECTRONS
  conv_thr      = {cfg.conv_thr}
  mixing_beta   = 0.4
  electron_maxstep = 120
/
! --- BACKEND MUST SPLICE BELOW BLOCKS FROM cif_path={cif_path} ---
! ATOMIC_SPECIES
! CELL_PARAMETERS {ry_scale}
! ATOMIC_POSITIONS crystal
K_POINTS automatic
  {cfg.kpoints[0]} {cfg.kpoints[1]} {cfg.kpoints[2]} 0 0 0
"""
