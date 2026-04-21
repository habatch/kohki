# Account Setup Checklist

Only **you** can do the steps marked **[YOU]**. Claude Code scaffolds
everything else. Follow top-to-bottom; each block is ~5–15 minutes.

---

## Prerequisites (one-time)

### [YOU] Install missing local tooling

Claude Code could not `sudo apt-get`. Run once:

```bash
sudo apt-get install -y python3-pip python3-venv jq zip
```

### [YOU] Anthropic API key

Paper 1 experiments run via direct API (not via Claude Code) for
reproducibility.

1. Go to https://console.anthropic.com/ → API Keys → Create Key
2. Copy the key (starts with `sk-ant-…`)
3. Store it:
   ```bash
   mkdir -p ~/.config/paper1
   chmod 700 ~/.config/paper1
   cat > ~/.config/paper1/anthropic.env <<'EOF'
   ANTHROPIC_API_KEY=sk-ant-xxxxxxxxx
   EOF
   chmod 600 ~/.config/paper1/anthropic.env
   ```

---

## Backend 1 — GitHub Actions (no cost, ~15 min setup)

Runs QE for small/medium systems in parallel via matrix jobs. Public repo
required for unlimited minutes.

### [YOU] Make the repo public (or create a fork)

The `habatch/kohki` repo is currently private. Option A is strongly
preferred because it gives unlimited Actions minutes; option B keeps the
repo private but caps at 2,000 min/month.

- **A (preferred).** `gh repo edit habatch/kohki --visibility public` —
  check there's no secret in git history first with
  `git log -p | grep -i -E '(key|secret|password|token)' | head`.
- **B.** Leave private, accept the 2,000 min/month cap.

### [CLAUDE] Create `.github/workflows/qe-batch.yml`

Already generated at `/home/kohki/.github/workflows/qe-batch.yml`. Commits
and pushes are **your** call.

### Verify

```bash
gh workflow list
gh workflow run qe-batch.yml -f tier=pilot -f material=Si
gh run watch
```

Expected: one job completes in ~3–5 min, outputs `Si.out` as an artifact.

---

## Backend 2 — Kaggle (no cost, ~10 min setup)

Free T4 GPU, 30 hrs/week, 12 h/session. Fits all Tier C (doped Si 64-atom).

### [YOU] Account + API token

1. Create free account at https://www.kaggle.com (any email).
2. Settings → Account → **Create New API Token**. Downloads `kaggle.json`.
3. Install:
   ```bash
   mkdir -p ~/.kaggle
   mv ~/Downloads/kaggle.json ~/.kaggle/    # or wherever the download went
   chmod 600 ~/.kaggle/kaggle.json
   ```
4. Verify from this machine:
   ```bash
   python3 -m pip install --user kaggle   # after pip is installed
   kaggle kernels list --mine
   ```

### [YOU] Enable internet on the notebook

Kaggle notebooks are offline by default. In the notebook UI right panel:
**Settings → Internet → On**. Required for Materials Project API + conda
install.

### [CLAUDE] Notebook source

Already generated at `notebooks/kaggle_qe_gpu.py`. The CLI converts it to
`.ipynb` and uploads via the Kaggle API — **you** approve the first push.

---

## Backend 3 — Oracle Cloud Always Free (no cost, ~25 min setup)

Permanent 4 ARM cores + 24 GB RAM. Runs as a 24/7 standing worker.
**Requires a credit card for identity verification, but never charged** as
long as you stay in the Always-Free envelope.

### [YOU] Account

1. https://www.oracle.com/cloud/free/
2. Sign-up (personal details + CC for verification). Choose a region with
   ARM Ampere A1 availability — `us-ashburn-1`, `us-phoenix-1`, and
   `ap-tokyo-1` typically have stock.
3. Once logged in, navigate to **Compute → Instances → Create Instance**.
4. Image: **Canonical Ubuntu 24.04 (aarch64)**.
5. Shape: **VM.Standard.A1.Flex → 4 OCPU, 24 GB**.
6. Networking: default VCN, public IPv4 yes.
7. SSH keys: upload your `~/.ssh/id_ed25519.pub` (generate one first if
   you don't have it: `ssh-keygen -t ed25519 -C paper1-oracle`).
8. **Boot volume cloud-init**: paste the contents of
   `scripts/oracle-cloud-init.sh` into the "user data" box.

ARM Ampere A1 capacity is sometimes exhausted. If create fails with
"Out of capacity", retry every few hours — not an account issue.

### Verify

```bash
ssh ubuntu@<instance-public-ip> 'pw.x -h | head -5'
```

Expected: QE help banner.

---

## Backend 4 — GCP $300 free credit (optional burst, ~20 min setup)

Use when GH Actions + Kaggle + Oracle isn't enough. $300 credit expires
after 90 days so only activate when you're ready to burn it.

### [YOU] Account

1. https://cloud.google.com/free → Get started for free.
2. Accept $300 / 90-day credit.
3. Install `gcloud`:
   ```bash
   curl https://sdk.cloud.google.com | bash
   exec -l $SHELL
   gcloud init
   ```
4. Enable Compute Engine API:
   ```bash
   gcloud services enable compute.googleapis.com
   ```
5. **Set a budget alert immediately** (Billing → Budgets → $50 / month
   hard cap).

### [CLAUDE] Startup script

Already generated at `scripts/gcp-startup.sh`. Launch a c4-highcpu-96
spot:

```bash
./scripts/gcp-vm-up.sh        # claude-generated helper
```

---

## Backend 5 — AWS Spot (optional burst, if you have credits)

Same as GCP but with AWS Cloud Credit for Research grant. Apply here:
https://aws.amazon.com/grants/credits-for-research/ (2-week wait).

### [YOU] AWS Academic / Research Credit application

1. Go to the grant URL, submit research plan (1 page of Paper 1 abstract
   is sufficient).
2. Wait 1–2 weeks.
3. When approved, create IAM user + access key, store as:
   ```bash
   aws configure     # after installing aws-cli
   ```

---

## Final verification

Once Backend 1 and Backend 2 are set up, run the pilot:

```bash
cd /home/kohki/research/paper1-benchmark
python3 -m orchestrator pilot --material Si --backend github
python3 -m orchestrator pilot --material GaAs --backend kaggle
```

Both should produce a provenance zip under `results/pilot/`.

---

## What Claude Code produces (already done)

| Path | Purpose |
|------|---------|
| `/home/kohki/.github/workflows/qe-batch.yml` | GH Actions QE runner |
| `orchestrator/*.py` | CLI + MP client + QE inputs + provenance |
| `llm/client.py` | Anthropic API direct-call wrapper |
| `materials/tier_*.yaml` | 100-material benchmark list |
| `notebooks/kaggle_qe_gpu.py` | Kaggle notebook source |
| `scripts/oracle-cloud-init.sh` | OCI bootstrap |
| `scripts/gcp-startup.sh` | GCE bootstrap |

## What you do (summary)

1. `sudo apt-get install -y python3-pip python3-venv jq zip`
2. Anthropic API key → `~/.config/paper1/anthropic.env`
3. Make `habatch/kohki` public (or accept 2k min/month)
4. Kaggle API token → `~/.kaggle/kaggle.json`
5. Oracle account → provision ARM instance with `oracle-cloud-init.sh`
6. (Optional) GCP free-trial activation
7. (Optional) AWS Research Credit application

Total user time: **~60 minutes** across all 7 steps.
