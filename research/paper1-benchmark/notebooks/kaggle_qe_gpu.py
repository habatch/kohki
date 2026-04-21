# Kaggle Notebook — Paper 1 QE runner (Tier C, doped Si supercells)
#
# This file is the source. To upload as a Kaggle notebook:
#
#     pip install kaggle
#     kaggle kernels push -p notebooks/
#
# `notebooks/kaggle-metadata.json` tells Kaggle this is a GPU-enabled
# Python script. Kaggle converts `.py` with `# %%` cell markers into a
# notebook on ingest.
#
# Weekly GPU budget: 30 hours. Session: 12 hours. Internet: must be ON
# (Notebook Settings → Internet → On) so conda-forge + MP API work.

# %% [markdown]
# # Paper 1 — DFT Ground Truth on Kaggle T4
#
# Runs a single material through QE (pw.x SCF, optionally NSCF + bands)
# and uploads the provenance zip as a Kaggle Dataset so downstream
# analysis can pick it up.

# %% Environment bootstrap
# Micromamba sets up QE in ~2 minutes. Caching it across sessions is
# possible via Kaggle Datasets once we're past the pilot.
import os, subprocess, sys, time
from pathlib import Path

os.environ["MAMBA_ROOT_PREFIX"] = "/opt/conda"
subprocess.run(
    ["curl", "-L", "-o", "/tmp/mm.tar.bz2",
     "https://micro.mamba.pm/api/micromamba/linux-64/latest"],
    check=True,
)
subprocess.run(["mkdir", "-p", "/opt/conda/bin"], check=True)
subprocess.run(
    ["tar", "-xjf", "/tmp/mm.tar.bz2", "-C", "/opt/conda", "bin/micromamba"],
    check=True,
)
MM = "/opt/conda/bin/micromamba"

subprocess.run(
    [MM, "create", "-y", "-n", "qe", "-c", "conda-forge",
     "python=3.12", "quantum-espresso=7.3", "ase", "spglib", "mpich"],
    check=True,
)

QE_BIN = subprocess.run(
    [MM, "run", "-n", "qe", "which", "pw.x"],
    check=True, capture_output=True, text=True,
).stdout.strip()
print(f"pw.x located at {QE_BIN}")


# %% Pull material + pseudos
MP_API_KEY = os.environ.get("MP_API_KEY")      # Kaggle "Add-ons → Secrets"
MATERIAL   = os.environ.get("PAPER1_MATERIAL", "Si")
MP_ID      = os.environ.get("PAPER1_MP_ID",  "mp-149")

assert MP_API_KEY, "Add MP_API_KEY as a Kaggle secret before running."

# We re-import the orchestrator utilities from GitHub. Because Kaggle
# doesn't clone the repo by default, we pin the commit and pull the
# relevant modules directly.
REPO_RAW = "https://raw.githubusercontent.com/habatch/kohki"
COMMIT   = os.environ.get("PAPER1_COMMIT", "main")

def fetch(rel):
    subprocess.run(
        ["curl", "-fsSL", "-o", Path(rel).name,
         f"{REPO_RAW}/{COMMIT}/research/paper1-benchmark/{rel}"],
        check=True,
    )

fetch("orchestrator/mp_client.py")
fetch("orchestrator/qe_inputs.py")
fetch("orchestrator/provenance.py")
fetch("orchestrator/materials.py")

sys.path.insert(0, ".")
from mp_client import MPClient  # noqa: E402
from qe_inputs import suggest_config  # noqa: E402
from provenance import bundle_dft_run, current_env  # noqa: E402

client = MPClient(api_key=MP_API_KEY)
cif = client.cif(MP_ID)
Path(f"{MATERIAL}.cif").write_text(cif)
print(f"wrote {MATERIAL}.cif ({len(cif)} bytes)")

# SSSP pseudos — download once per session
subprocess.run(
    ["curl", "-L", "-o", "sssp.tar.gz",
     "https://archive.materialscloud.org/record/file"
     "?filename=SSSP_1.3.0_PBE_efficiency.tar.gz&record_id=1732"],
    check=True,
)
Path("pseudo").mkdir(exist_ok=True)
subprocess.run(
    ["tar", "-xzf", "sssp.tar.gz", "-C", "pseudo", "--strip-components=1"],
    check=True,
)


# %% Build the QE input
from ase.io import read, write
atoms = read(f"{MATERIAL}.cif")
elements = sorted({a.symbol for a in atoms})
cfg = suggest_config(elements)
pseudos = {el: f"{el}.upf" for el in elements}

# Symlink pseudos into a single dir with expected names
import re, shutil
for upf in Path("pseudo").glob("*.upf"):
    m = re.match(r"([A-Z][a-z]?)[_.].*\.upf$", upf.name)
    if m:
        dst = Path("pseudo") / f"{m.group(1)}.upf"
        if not dst.exists() or dst.samefile(upf):
            shutil.copy(upf, dst)

write(
    f"{MATERIAL}.scf.in",
    atoms,
    format="espresso-in",
    input_data={
        "calculation": "scf",
        "prefix": MATERIAL,
        "pseudo_dir": "./pseudo",
        "outdir": "./tmp",
        "ecutwfc": cfg.ecutwfc,
        "ecutrho": cfg.ecutrho,
        "occupations": "smearing",
        "smearing": cfg.smearing,
        "degauss": cfg.degauss,
        "conv_thr": cfg.conv_thr,
        "mixing_beta": 0.4,
    },
    pseudopotentials=pseudos,
    kpts=list(cfg.kpoints),
)


# %% Run pw.x
t0 = time.time()
proc = subprocess.run(
    [MM, "run", "-n", "qe", "mpirun", "-n", "4", "--oversubscribe",
     "pw.x", "-in", f"{MATERIAL}.scf.in"],
    capture_output=True, text=True,
)
wall = time.time() - t0
Path(f"{MATERIAL}.scf.out").write_text(proc.stdout + proc.stderr)
print(f"pw.x wall = {wall:.1f}s, exit = {proc.returncode}")
assert proc.returncode == 0, proc.stderr[-2000:]


# %% Bundle and emit to /kaggle/working so Kaggle uploads it as output
env = current_env()
bundle = bundle_dft_run(
    Path("/kaggle/working/bundles"),
    material=MATERIAL,
    qe_input=Path(f"{MATERIAL}.scf.in").read_text(),
    qe_output=Path(f"{MATERIAL}.scf.out").read_text(),
    observables={"wall_seconds": wall},
    env=env,
)
print(f"provenance bundle: {bundle}")
