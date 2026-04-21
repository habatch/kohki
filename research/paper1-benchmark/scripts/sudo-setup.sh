#!/usr/bin/env bash
# Run ONCE with sudo: installs system packages Claude Code cannot.
# Safe to re-run (apt-get skips already-installed).
set -euo pipefail
echo "Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
  python3-pip python3-venv \
  zip unzip xz-utils \
  build-essential gfortran libopenblas-dev \
  libfftw3-dev libopenmpi-dev openmpi-bin \
  pkg-config
echo
echo "System install complete. Verify with:"
echo "  pip3 --version  mpirun --version  unzip -v | head -1"
