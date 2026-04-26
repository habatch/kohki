#!/usr/bin/env bash
# 一時 swap (/swapfile) を完全削除して元の状態に戻す.
#
# Track A Phase 2 calibration 完了後 必須実行。
# SSD 寿命保護のため不要な swap は速やかに削除する。
#
# 使い方:
#   sudo bash scripts/swap_cleanup.sh
# Claude Code 内なら:
#   ! sudo bash /home/kohki/research/paper1-benchmark/scripts/swap_cleanup.sh

set -euo pipefail

SWAPFILE="/swapfile"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: must be run as root (use sudo)" >&2
  exit 1
fi

if [[ ! -e "$SWAPFILE" ]]; then
  echo "INFO: $SWAPFILE does not exist. Nothing to clean up."
  exit 0
fi

echo "== Before cleanup =="
swapon --show
free -h | head -2
echo

echo "== swapoff $SWAPFILE =="
swapoff "$SWAPFILE"
echo "== rm $SWAPFILE =="
rm -f "$SWAPFILE"

echo
echo "== After =="
swapon --show
free -h | head -2
echo
echo "OK. /swapfile 完全削除済み。元の swap (/dev/sdb) のみが有効です。"
