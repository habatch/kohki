#!/usr/bin/env bash
# Fetch SG15 ONCV PBE-1.2 pseudopotentials needed for Track A Phase 2.
#
# Existing in materials/pseudos/:
#   As, Cs, Ga, I, N, Pb, Si  (7 elements)
#
# Phase 2 N=10 plan needs additionally:
#   Tier A: Ge (mp-32 Ge), Al (AlN), Zn + O (ZnO)
#   Tier B: Mo + S (MoS2),  Bi + V (BiVO4; O reused)
#   Tier C: P (Si63P1), B (Si63B1)
#
# Total new DL: Ge, Al, Zn, O, Mo, S, Bi, V, P, B  (10 elements)
#
# Source: SG15 ONCV PBE-1.2 hosted by Schlipf-Gygi at quantum-simulation.org
#   http://www.quantum-simulation.org/potentials/sg15_oncv/upf/{Element}_ONCV_PBE-1.2.upf
#
# Usage:
#   bash scripts/fetch_pseudos.sh             # fetch missing only
#   bash scripts/fetch_pseudos.sh --force     # re-download all listed
#
# Idempotent: skips files that already exist (unless --force).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="$REPO_ROOT/materials/pseudos"
BASE_URL="http://www.quantum-simulation.org/potentials/sg15_oncv/upf"

ELEMENTS=(Ge Al Zn O Mo S Bi V P B)

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
fi

mkdir -p "$DEST_DIR"

echo "== SG15 ONCV PBE-1.2 fetcher =="
echo "Destination: $DEST_DIR"
echo "Elements: ${ELEMENTS[*]}"
echo

ok=0
skipped=0
failed=0

for el in "${ELEMENTS[@]}"; do
  fname="${el}_ONCV_PBE-1.2.upf"
  out="$DEST_DIR/$fname"
  url="$BASE_URL/$fname"

  if [[ -f "$out" && $FORCE -eq 0 ]]; then
    echo "  [skip] $fname (exists)"
    skipped=$((skipped + 1))
    continue
  fi

  echo "  [get ] $fname  <-  $url"
  if curl -fsSL "$url" -o "$out.tmp"; then
    # Sanity: must start with <UPF tag (avoid HTML 404 pages saved as UPF).
    if head -1 "$out.tmp" | grep -q "<UPF"; then
      mv "$out.tmp" "$out"
      ok=$((ok + 1))
    else
      echo "  [FAIL] $fname (not a UPF file — server returned HTML?)"
      rm -f "$out.tmp"
      failed=$((failed + 1))
    fi
  else
    echo "  [FAIL] $fname (curl error)"
    rm -f "$out.tmp"
    failed=$((failed + 1))
  fi
done

echo
echo "Summary: ok=$ok skipped=$skipped failed=$failed"

if [[ $failed -gt 0 ]]; then
  echo "Some downloads failed. Check network or URL availability."
  exit 1
fi

echo "Done. New pseudos written to $DEST_DIR"
