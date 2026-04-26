"""Parse a ``pw.x`` stdout (`.out`) into a handful of observables.

Kept intentionally small and stdlib-only. We extract what Paper 1 actually
benchmarks; anything else (bands, forces, stress) is out of scope.

Observables returned::

    {
        "converged":        True / False,
        "n_scf_iter":       int,
        "total_energy_Ry":  float,
        "fermi_energy_eV":  float | None,
        "homo_eV":          float | None,   # highest-occupied (insulators)
        "lumo_eV":          float | None,
        "band_gap_eV":      float | None,
        "n_electrons":      float | None,
        "alat_bohr":        float | None,
        "volume_A3":        float | None,
        "wall_seconds":     float | None,
        "cpu_seconds":      float | None,
        "qe_version":       str | None,
        "n_atoms":          int | None,
        "n_kpoints":        int | None,
    }
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


# Regex catalogue. Each pattern is used with ``re.search`` / ``findall`` as
# noted — grouped by what we extract.
RE_TOTAL_E = re.compile(r"^!\s+total energy\s+=\s+(-?\d+\.\d+)\s+Ry", re.MULTILINE)
RE_FERMI   = re.compile(r"the Fermi energy is\s+(-?\d+\.\d+)\s*ev", re.IGNORECASE)
RE_HOMO_LUMO = re.compile(
    r"highest occupied,?\s*lowest unoccupied level.*?:\s+"
    r"(-?\d+\.\d+)\s+(-?\d+\.\d+)",
    re.IGNORECASE,
)
RE_HOMO_ONLY = re.compile(
    r"highest occupied level \(ev\)\s*:\s*(-?\d+\.\d+)",
    re.IGNORECASE,
)
RE_CONV = re.compile(r"convergence has been achieved in\s+(\d+)\s+iterations")
RE_NELECT = re.compile(r"number of electrons\s*=\s*(\d+\.\d+)")
RE_ALAT   = re.compile(r"lattice parameter \(alat\)\s*=\s*(\d+\.\d+)\s*a\.u\.")
RE_VOLUME = re.compile(r"unit-cell volume\s*=\s*(\d+\.\d+)\s*\(a\.u\.\)")
RE_NATOMS = re.compile(r"number of atoms/cell\s*=\s*(\d+)")
RE_NKP    = re.compile(r"number of k points=\s*(\d+)")
RE_VERSION = re.compile(r"Program PWSCF v\.(\S+)\s+starts")

# pw.x が SCF iteration 開始前に reject するエラーパターン (LLM 提案
# params が物理的に成立しない場合に発生)。これらは「未収束」とは別の
# "unphysical_proposal" カテゴリで集計する。
PRE_SCF_ERROR_PATTERNS = [
    (re.compile(r"Error in routine memory_report.*more bands than PWs",
                re.DOTALL | re.IGNORECASE), "more_bands_than_pws"),
    (re.compile(r"Error in routine readpp.*file\s+\S+\s+not\s+found",
                re.DOTALL | re.IGNORECASE), "missing_pseudo"),
    (re.compile(r"Error in routine\s+set_kpoint", re.IGNORECASE), "kpoint_error"),
    (re.compile(r"Error in routine\s+(\w+)\s+\(\d+\)", re.IGNORECASE), "generic_pre_scf_error"),
]
# QE prints PWSCF timing in several forms:
#   "PWSCF  :  9m19.66s CPU   4m41.49s WALL"    (short runs)
#   "PWSCF  :  2h45m CPU      1h21m WALL"        (long runs, no seconds)
#   "PWSCF  :  45.23s CPU      23.01s WALL"      (trivial runs)
# We parse lazily: h, m, s fragments each optional so long as ≥1 is present.
RE_PWSCF_CPU = re.compile(
    r"PWSCF\s*:\s*"
    r"((?:\d+h\s*)?(?:\d+m\s*)?(?:[\d.]+s)?)\s*CPU\s+"
    r"((?:\d+h\s*)?(?:\d+m\s*)?(?:[\d.]+s)?)\s*WALL"
)
_DURATION_RE = re.compile(r"(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:([\d.]+)s)?")


BOHR_TO_ANG = 0.529177210903


@dataclass
class Observables:
    converged: bool
    n_scf_iter: int | None
    total_energy_Ry: float | None
    fermi_energy_eV: float | None
    homo_eV: float | None
    lumo_eV: float | None
    band_gap_eV: float | None
    n_electrons: float | None
    alat_bohr: float | None
    alat_ang: float | None
    volume_A3: float | None
    wall_seconds: float | None
    cpu_seconds: float | None
    qe_version: str | None
    n_atoms: int | None
    n_kpoints: int | None
    pre_scf_error: str | None = None    # LLM 提案 params が物理的に不適切で
                                         # pw.x が SCF 開始前に reject した場合

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _last_float(pattern: re.Pattern[str], text: str) -> float | None:
    matches = pattern.findall(text)
    return float(matches[-1]) if matches else None


def _last_int(pattern: re.Pattern[str], text: str) -> int | None:
    matches = pattern.findall(text)
    return int(matches[-1]) if matches else None


def _parse_duration(s: str) -> float | None:
    """Parse strings like '2h45m', '9m19.66s', '45.23s' into seconds."""
    s = s.strip()
    if not s:
        return None
    m = _DURATION_RE.fullmatch(s)
    if not m:
        return None
    h, mn, sec = m.groups()
    total = 0.0
    if h:   total += int(h) * 3600
    if mn:  total += int(mn) * 60
    if sec: total += float(sec)
    return total if (h or mn or sec) else None


def _parse_pwscf_timing(text: str) -> tuple[float | None, float | None]:
    m = RE_PWSCF_CPU.search(text)
    if not m:
        return None, None
    cpu = _parse_duration(m.group(1))
    wall = _parse_duration(m.group(2))
    return wall, cpu


def parse_pw_output(text: str) -> Observables:
    """Parse a pw.x stdout/log into :class:`Observables`.

    Forgiving: missing fields surface as ``None`` rather than raising.
    """
    total_E = _last_float(RE_TOTAL_E, text)
    fermi   = _last_float(RE_FERMI, text)

    # HOMO / LUMO — accept either the combined line ("highest occupied,
    # lowest unoccupied") or a lone HOMO line (for gapless systems where
    # QE drops the LUMO column).
    homo: float | None = None
    lumo: float | None = None
    m = RE_HOMO_LUMO.search(text)
    if m:
        homo, lumo = float(m.group(1)), float(m.group(2))
    else:
        m2 = RE_HOMO_ONLY.search(text)
        if m2:
            homo = float(m2.group(1))

    gap = (lumo - homo) if (homo is not None and lumo is not None) else None

    wall_s, cpu_s = _parse_pwscf_timing(text)

    alat_bohr = _last_float(RE_ALAT, text)
    alat_ang = alat_bohr * BOHR_TO_ANG if alat_bohr is not None else None
    vol_au3 = _last_float(RE_VOLUME, text)
    vol_A3 = vol_au3 * (BOHR_TO_ANG**3) if vol_au3 is not None else None

    conv_m = RE_CONV.search(text)
    n_iter = int(conv_m.group(1)) if conv_m else None

    ver_m = RE_VERSION.search(text)

    # pre-SCF error 検出 (SCF 反復が一度も走っていない場合のエラー識別)
    pre_scf_error: str | None = None
    if not conv_m and total_E is None:
        for pattern, label in PRE_SCF_ERROR_PATTERNS:
            if pattern.search(text):
                pre_scf_error = label
                break

    return Observables(
        converged=conv_m is not None,
        n_scf_iter=n_iter,
        total_energy_Ry=total_E,
        fermi_energy_eV=fermi,
        homo_eV=homo,
        lumo_eV=lumo,
        band_gap_eV=gap,
        n_electrons=_last_float(RE_NELECT, text),
        alat_bohr=alat_bohr,
        alat_ang=alat_ang,
        volume_A3=vol_A3,
        wall_seconds=wall_s,
        cpu_seconds=cpu_s,
        qe_version=ver_m.group(1) if ver_m else None,
        n_atoms=_last_int(RE_NATOMS, text),
        n_kpoints=_last_int(RE_NKP, text),
        pre_scf_error=pre_scf_error,
    )


def parse_pw_file(path: str | Path) -> Observables:
    return parse_pw_output(Path(path).read_text(errors="replace"))
