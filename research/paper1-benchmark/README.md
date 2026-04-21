# Paper 1: LLM × DFT Benchmark

Infrastructure for "Self-verifying AI for DFT" — Paper 1 scope.
Measures how accurately LLMs recall / predict semiconductor & photovoltaic
material properties vs Quantum ESPRESSO PBE ground truth.

## Pipeline in one picture

```
 materials/tier_*.yaml
        │
        ├─► Materials Project API ──► PBE ground truth (Tier A free)
        │
        └─► QE input generator
                 │
     ┌───────────┼────────────┬────────────┬───────────┐
     ▼           ▼            ▼            ▼           ▼
  local      GitHub       Kaggle      Oracle       GCP/AWS
  (pilot)   Actions     T4 GPU      Always Free   (spot)
     │           │            │            │           │
     └───────────┴────────────┴────────────┴───────────┘
                             │
                        provenance.zip
                             │
                   ┌─────────┴──────────┐
                   ▼                    ▼
            LLM prediction      Ground-truth DFT
            (Anthropic API,     (Fermi, gap, m*,
             temp=0, pinned)    formation E, …)
                   └─────────┬──────────┘
                             ▼
                       diff analysis
                             │
                             ▼
                     paper1 figures
```

## Layout

```
paper1-benchmark/
├── README.md
├── SETUP.md                      # per-provider account setup checklist
├── materials/
│   ├── tier_a.yaml               # 20 classic semiconductors
│   ├── tier_b.yaml               # 40 PV / emerging
│   └── tier_c.yaml               # 40 doped-Si supercells (generated)
├── orchestrator/
│   ├── cli.py                    # `python3 -m orchestrator …` entry
│   ├── materials.py              # load & validate material lists
│   ├── mp_client.py              # Materials Project API (stdlib-only)
│   ├── qe_inputs.py              # CIF → pw.in / pw.dos / pw.bands
│   ├── provenance.py             # SHA-256 tagged JSONL + zip bundle
│   └── backends/
│       ├── local.py              # run on this laptop (pilot)
│       ├── github_actions.py     # `gh workflow run` dispatch
│       └── kaggle.py             # push / run Kaggle kernel
├── llm/
│   ├── client.py                 # Anthropic API, temperature=0, pinned model id
│   └── prompts.py                # benchmark prompt templates
├── notebooks/
│   └── kaggle_qe_gpu.py          # source for the Kaggle notebook
├── scripts/
│   ├── oracle-cloud-init.sh      # cloud-init for OCI Always Free ARM
│   ├── gcp-startup.sh            # GCE startup script
│   └── aws-spot-launch.sh        # EC2 Spot launcher
└── results/                      # gitignored — raw outputs & bundles
```

## Hard rules (Paper 3 provenance requirements)

1. **Every LLM call** is logged as a single JSONL line with:
   `{prompt_sha, response, model_id_pinned, temperature, seed, tool_versions}`.
2. **Every DFT calc** is bundled as a zip with:
   `{input.in, output.out, charge-density.hdf5, metadata.yaml}` where the
   yaml includes commit hash of this repo, QE version, conda env hash, wall time.
3. **No tool or model ID may be abbreviated** — always use the full dated
   ID, e.g. `claude-opus-4-7-20260419`, `quantum-espresso-7.3.1`.
4. **Experiment code runs via Anthropic API direct-call only.** Claude Code
   (this tool) is for scaffolding, never for the benchmark itself.

## Compute plan (free-tier stacking)

| Stage | Backend | Why | Weekly budget |
|-------|---------|-----|---------------|
| Tier A ground truth | Materials Project | already computed, no DFT needed | 0 |
| Tier B ground truth | GitHub Actions ×20 parallel | 6h/job, public repo | ~20 hours wall |
| Tier C ground truth | Kaggle T4 + QE-GPU | 30 GPU-hrs/week × ~10× CPU | 30 GPU-hrs |
| Standing batch | Oracle Always Free (4 ARM) | 24/7 free | continuous |
| LLM predictions | Anthropic API | primary experiment | N/A |

Expected full Paper-1 completion: **2 weeks wall clock, $0.**

## Status

See `SETUP.md` for account-setup checklist (what only **you** can do).
See `docs/PROJECT-STATE.md` for live progress.
