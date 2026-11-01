#!/usr/bin/env bash
# Start 4 QBFT validators on localhost: p2p 30303-30306, RPC 8545-8548 (127.0.0.1 only).
set -euo pipefail
cd "$(dirname "$0")"
BESU_BIN="${BESU_BIN:?Set BESU_BIN}"
export BESU_OPTS="${BESU_OPTS:--Xmx384m}"
mkdir -p logs pids
PUB=$(cat networkFiles/keys/$(ls networkFiles/keys | sort | head -1)/key.pub | sed 's/^0x//')
BOOT="enode://${PUB}@127.0.0.1:30303"
for i in 1 2 3 4; do
  if [ -f pids/node$i.pid ] && kill -0 "$(cat pids/node$i.pid)" 2>/dev/null; then echo "node$i already running"; continue; fi
  EXTRA=""; [ "$i" != 1 ] && EXTRA="--bootnodes=$BOOT"
  setsid nohup "$BESU_BIN" --data-path=nodes/node$i/data --genesis-file=networkFiles/genesis.json \
    --node-private-key-file=nodes/node$i/data/key --network-id=20260 \
    --p2p-host=127.0.0.1 --p2p-port=$((30302+i)) --min-gas-price=0 \
    --rpc-http-enabled --rpc-http-host=127.0.0.1 --rpc-http-port=$((8544+i)) --rpc-http-api=ETH,NET,QBFT,WEB3 \
    $EXTRA > logs/node$i.log 2>&1 &
  echo $! > pids/node$i.pid
  echo "started node$i (pid $(cat pids/node$i.pid))"
  if [ "$i" = 1 ]; then sleep 12; fi
done
