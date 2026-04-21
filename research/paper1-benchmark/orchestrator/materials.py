"""Load the Paper 1 material lists.

Materials live in ``materials/tier_{a,b,c}.toml`` and are read with the
stdlib ``tomllib`` (Python ≥ 3.11). Each file has the same shape::

    [[material]]
    formula   = "Si"
    structure = "diamond"
    tier      = "A"
    mp_id     = "mp-149"            # optional; omit for custom cells
    cif       = "fixtures/Si.cif"   # optional; filled when cached
    notes     = "..."
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Material:
    formula: str
    structure: str
    tier: str
    mp_id: str | None = None
    cif: str | None = None
    notes: str = ""
    # Arbitrary extra fields land here so we don't lose user-added keys.
    extra: dict[str, object] = field(default_factory=dict)


def _parse_entries(raw: dict[str, object], tier: str, source: Path) -> list[Material]:
    entries = raw.get("material")
    if not isinstance(entries, list):
        raise ValueError(f"{source}: expected a [[material]] array, got {type(entries)!r}")
    out: list[Material] = []
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            raise ValueError(f"{source} entry {i}: not a table")
        known = {"formula", "structure", "tier", "mp_id", "cif", "notes"}
        missing = {"formula", "structure"} - e.keys()
        if missing:
            raise ValueError(f"{source} entry {i}: missing fields {missing}")
        out.append(
            Material(
                formula=str(e["formula"]),
                structure=str(e["structure"]),
                tier=str(e.get("tier", tier)),
                mp_id=(str(e["mp_id"]) if "mp_id" in e else None),
                cif=(str(e["cif"]) if "cif" in e else None),
                notes=str(e.get("notes", "")),
                extra={k: v for k, v in e.items() if k not in known},
            )
        )
    return out


def load_tier(tier: str, root: Path | None = None) -> list[Material]:
    root = root or _default_root()
    path = root / f"tier_{tier.lower()}.toml"
    with path.open("rb") as f:
        raw = tomllib.load(f)
    return _parse_entries(raw, tier=tier.upper(), source=path)


def load_all(root: Path | None = None) -> list[Material]:
    root = root or _default_root()
    out: list[Material] = []
    for t in ("a", "b", "c"):
        path = root / f"tier_{t}.toml"
        if path.exists():
            out.extend(load_tier(t, root))
    return out


def _default_root() -> Path:
    return Path(__file__).resolve().parent.parent / "materials"
