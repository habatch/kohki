"""Paper 1 benchmark prompt templates.

Keep these **immutable once a run is started**. Any edit = new prompt
hash = new experiment. Version each template by filename suffix
(``v1``, ``v2`` …) rather than editing in place.

The goal is JSON-parseable output so downstream analysis stays
mechanical. We ask for numeric values **and** the LLM's stated
confidence so we can separate "LLM is wrong but certain" (a paper
finding) from "LLM is wrong and uncertain" (expected behaviour).
"""

from __future__ import annotations

SYSTEM_V1 = (
    "You are answering a materials-science benchmark. "
    "Respond ONLY with a valid JSON object matching the requested schema. "
    "No prose, no code fences, no commentary. "
    "Every numeric answer must include its unit. "
    "If you do not know, say so explicitly — do not guess."
)

PREDICT_PROPERTIES_V1 = """Predict PBE-DFT ground-state properties for the
following material, using your training data only (no tool use).

Material formula: {formula}
Crystal structure: {structure}

Return a JSON object with EXACTLY these keys:

{{
  "band_gap_eV":                 <number | null>,
  "is_gap_direct":               <true | false | null>,
  "lattice_constant_A":          <number | null>,
  "formation_energy_per_atom_eV":<number | null>,
  "cohesive_energy_per_atom_eV": <number | null>,
  "confidence_0_to_1":           <number>,
  "rationale":                   "<= 240 chars"
}}

Notes:
- All values MUST be what a typical PBE calculation would yield, NOT the
  experimental value. For gaps this generally means 30-50% smaller than
  experiment.
- Use null when you genuinely do not know — null counts better than a
  wrong guess for this benchmark.
- ``confidence`` is your self-reported probability that every non-null
  value above is within 20% of the true PBE value.
"""


def render_predict_properties(formula: str, structure: str) -> str:
    return PREDICT_PROPERTIES_V1.format(formula=formula, structure=structure)
