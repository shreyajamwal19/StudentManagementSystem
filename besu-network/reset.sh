#!/usr/bin/env bash
# DESTRUCTIVE: deletes chain data, validator keys and logs of the local dev network.
cd "$(dirname "$0")"; ./stop.sh; rm -rf networkFiles nodes logs pids; echo "network reset"
