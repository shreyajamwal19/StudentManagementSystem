#!/usr/bin/env bash
cd "$(dirname "$0")"
for i in 1 2 3 4; do
  [ -f pids/node$i.pid ] && kill "$(cat pids/node$i.pid)" 2>/dev/null && echo "stopped node$i"; rm -f pids/node$i.pid
done
