#!/usr/bin/env bash
# 一時的に 8 GB の swap を /swapfile に追加.
#
# Track A Phase 2 calibration (phi4:14b on 8 GB RAM 環境) のためだけに使う。
# 実験終了後に scripts/swap_cleanup.sh を必ず実行すること。
#
# 使い方 (sudo パスワード要):
#   sudo bash scripts/swap_setup.sh
# Claude Code 内なら:
#   ! sudo bash /home/kohki/research/paper1-benchmark/scripts/swap_setup.sh

set -euo pipefail

SWAPFILE="/swapfile"
SIZE_GB=8

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: must be run as root (use sudo)" >&2
  exit 1
fi

if [[ -e "$SWAPFILE" ]]; then
  echo "ERROR: $SWAPFILE already exists. Run swap_cleanup.sh first." >&2
  exit 2
fi

echo "== Pre-check =="
df -h / | head -2
free -h | head -2
echo

echo "== Allocate ${SIZE_GB} GB at $SWAPFILE =="
fallocate -l "${SIZE_GB}G" "$SWAPFILE"
chmod 600 "$SWAPFILE"
mkswap "$SWAPFILE"
swapon "$SWAPFILE"

echo
echo "== After =="
swapon --show
free -h | head -2
echo
echo "OK. 実験終了後は scripts/swap_cleanup.sh を必ず実行してください。"
