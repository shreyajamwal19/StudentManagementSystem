#!/usr/bin/env bash
# Generate the QBFT genesis + 4 validator keys (keys are secrets: they stay in networkFiles/, which is gitignored).
set -euo pipefail
cd "$(dirname "$0")"
BESU_BIN="${BESU_BIN:?Set BESU_BIN to the besu launcher, e.g. /opt/besu-26.10.2/bin/besu}"
[ -e networkFiles ] && { echo "networkFiles/ exists. Run ./reset.sh first (destructive: deletes chain data and keys)."; exit 1; }
"$BESU_BIN" operator generate-blockchain-config --config-file=qbftConfigFile.json --to=networkFiles --private-key-file-name=key
i=1
for d in $(ls -d networkFiles/keys/0x* | sort); do
  mkdir -p nodes/node$i/data
  cp "$d/key" nodes/node$i/data/key
  echo "node$i -> $(basename "$d")"
  i=$((i+1))
done
echo "Genesis: networkFiles/genesis.json"
