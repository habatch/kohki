"""Minimal Materials Project v2 REST client (stdlib only).

The canonical ``mp-api`` pip package is heavier and pulls in pymatgen at
import time. We only need three things for Paper 1:

1. Resolve a formula / material id to its canonical ``material_id`` and
   ``formula_pretty``.
2. Pull PBE ground-truth observables: ``band_gap``, ``formation_energy_per_atom``,
   ``is_gap_direct``, ``is_metal``, ``volume``, ``density``.
3. Download the relaxed structure as a CIF string.

Docs: https://api.materialsproject.org/docs
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

BASE = "https://api.materialsproject.org"


@dataclass
class MPSummary:
    material_id: str
    formula_pretty: str
    band_gap: float | None
    formation_energy_per_atom: float | None
    is_gap_direct: bool | None
    is_metal: bool | None
    volume: float | None
    density: float | None
    symmetry: str | None
    raw: dict[str, Any]


class MPClient:
    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self.api_key = api_key or os.environ.get("MP_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "MP_API_KEY not set. Get one at https://next-gen.materialsproject.org/api"
            )
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "X-API-KEY": self.api_key,
                "accept": "application/json",
                "user-agent": "paper1-benchmark/0.1",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    def summary(self, material_id: str) -> MPSummary:
        """Fetch the summary document for a single material id (``mp-149`` etc.)."""
        # The v2 summary endpoint accepts material_ids as a comma-separated
        # list; we pass exactly one.
        data = self._get(
            "/materials/summary/",
            {
                "material_ids": material_id,
                "_fields": (
                    "material_id,formula_pretty,band_gap,"
                    "formation_energy_per_atom,is_gap_direct,is_metal,"
                    "volume,density,symmetry"
                ),
            },
        )
        docs = data.get("data") or []
        if not docs:
            raise LookupError(f"MP summary empty for {material_id}")
        d = docs[0]
        sym = d.get("symmetry") or {}
        return MPSummary(
            material_id=d["material_id"],
            formula_pretty=d.get("formula_pretty", ""),
            band_gap=d.get("band_gap"),
            formation_energy_per_atom=d.get("formation_energy_per_atom"),
            is_gap_direct=d.get("is_gap_direct"),
            is_metal=d.get("is_metal"),
            volume=d.get("volume"),
            density=d.get("density"),
            symmetry=sym.get("symbol") if isinstance(sym, dict) else None,
            raw=d,
        )

    def cif(self, material_id: str) -> str:
        """Return the CIF representation of the conventional cell."""
        data = self._get(f"/materials/summary/{material_id}/", {"_fields": "structure"})
        struct = (data.get("data") or [{}])[0].get("structure")
        if not struct:
            raise LookupError(f"MP structure missing for {material_id}")
        # The API returns a pymatgen-style dict; convert to CIF via a small
        # shim so we don't pull in pymatgen as a dep.
        return _structure_dict_to_cif(struct, material_id)


def _structure_dict_to_cif(struct: dict[str, Any], mp_id: str) -> str:
    """Render a Materials Project structure dict as a minimal CIF P1 block.

    This is enough for QE to read via ASE or quantum-espresso's internal
    CIF parser. Symmetry is intentionally downgraded to P1; the caller can
    refine later with spglib if needed.
    """
    lattice = struct.get("lattice", {})
    a = lattice.get("a"); b = lattice.get("b"); c = lattice.get("c")
    al = lattice.get("alpha"); be = lattice.get("beta"); ga = lattice.get("gamma")
    sites = struct.get("sites", [])
    atoms: list[tuple[str, float, float, float]] = []
    for s in sites:
        label = s.get("label") or (s.get("species") or [{}])[0].get("element") or "X"
        frac = s.get("abc") or s.get("frac_coords") or [0.0, 0.0, 0.0]
        atoms.append((str(label), float(frac[0]), float(frac[1]), float(frac[2])))

    lines = [
        f"data_{mp_id}",
        "_symmetry_space_group_name_H-M   'P 1'",
        "_symmetry_Int_Tables_number      1",
        f"_cell_length_a                  {a:.6f}" if a else "",
        f"_cell_length_b                  {b:.6f}" if b else "",
        f"_cell_length_c                  {c:.6f}" if c else "",
        f"_cell_angle_alpha               {al:.4f}" if al else "",
        f"_cell_angle_beta                {be:.4f}" if be else "",
        f"_cell_angle_gamma               {ga:.4f}" if ga else "",
        "loop_",
        "_atom_site_label",
        "_atom_site_fract_x",
        "_atom_site_fract_y",
        "_atom_site_fract_z",
    ]
    for lab, x, y, z in atoms:
        lines.append(f"{lab} {x:.6f} {y:.6f} {z:.6f}")
    return "\n".join(l for l in lines if l) + "\n"
