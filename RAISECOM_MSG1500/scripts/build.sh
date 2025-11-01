#!/usr/bin/env bash
set -euo pipefail
# Run from inside the OpenWrt buildroot that matches this CCS.
# 1) Update & install feeds
./scripts/feeds update -a
./scripts/feeds install -a
# 2) Apply config
if [[ -f "../configs/diffconfig" ]]; then
  cp ../configs/diffconfig .config
  make defconfig
fi
# 3) Merge public overlay (if provided next to the tree)
if [[ -d "../files-public" ]]; then
  rsync -a ../files-public/ ./files/
fi
# 4) Build
make -j"$(nproc)"
