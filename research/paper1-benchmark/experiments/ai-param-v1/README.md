# Experiment: ai-param-v1

**Objective.** Measure the quality of LLM-chosen Quantum ESPRESSO input
parameters by running QE with LLM-proposed settings on a small set of
benchmark materials, while keeping every other element of the pipeline
deterministic. The "quality" metrics are:

- Did pw.x converge? (binary)
- How many SCF iterations? (efficiency proxy)
- Total energy, Fermi energy, lattice fit — are they within expected
  PBE bounds vs the rule-based baseline?

## Contamination boundary

| Component | Who decides | Notes |
|-----------|-------------|-------|
| ecutwfc / ecutrho | **LLM** | Per-material |
| k-points | **LLM** | Per-material |
| smearing + degauss | **LLM** | |
| conv_thr | **LLM** | |
| mixing_beta | **LLM** | |
| CIF (crystal structure) | frozen | `materials/fixtures/{formula}.cif` |
| Pseudopotentials | frozen | SG15 ONCV PBE-1.2, SHA-256 pinned via git |
| pw.x binary | frozen | conda-forge qe (version recorded in provenance) |
| Post-processing | deterministic | `orchestrator/qe_parser.py` |

The LLM is confined to the input-parameter block. The physics-producing
code paths (pw.x, its pseudopotentials, the CIF lattice / atomic
coordinates) never see an LLM output.

## Protocol

1. For each material M in `predictions/`, a JSON record was produced by
   the LLM. The record includes: prompt, full response, extracted
   parameters, model_id, timestamp, reasoning.
2. The GitHub Actions workflow `ai-param-experiment.yml` reads these
   JSONs directly (NOT `suggest_config`) and writes them into the pw.x
   `&SYSTEM` / `&ELECTRONS` / `K_POINTS` blocks. Atomic positions still
   come from the deterministic CIF.
3. pw.x runs SCF. Output is bundled with metadata into
   `results/{formula}.zip`.
4. `orchestrator/qe_parser.py` extracts observables. A cross-material
   `summary.jsonl` lands alongside the zips.

## LLM provenance caveat (v1)

**This first run uses Claude Code's in-session model as the LLM.**
Specifically, the ``llm.model_id`` field in each prediction JSON records
``claude-opus-4-7[1m] (Claude Code CLI session, non-reproducible)``.
Per the project's separation-of-concerns rule, this is a **demo**: the
exact numerical LLM outputs cannot be re-derived because Claude Code
does not pin temperature=0 or a dated model id.

When `ANTHROPIC_API_KEY` is configured, the same protocol re-runs via
`llm/client.py::AnthropicClient` with a dated model id and
temperature=0, producing comparable **reproducible** data (which is what
any paper submission will use). The JSON schema is identical between
versions so both runs can be ingested into the same analysis.

## Materials in this trial

| Formula | Cell | #atoms | Notes |
|---------|------|--------|-------|
| Si       | diamond primitive   | 2 | covalent, light — calibration baseline |
| GaAs     | zincblende primitive| 2 | direct gap, Ga 3d semicore — moderate |
| CsPbI3   | perovskite cubic    | 5 | heavy Pb, halide — Tier B challenge |

Each also has a rule-based counterpart (from earlier runs) to diff
against.
