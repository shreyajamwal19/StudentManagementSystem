#!/usr/bin/env bash
# Lightweight pre-commit secret scan over staged changes. Exit 1 if a likely secret is found.
# Flags: GitHub tokens, PEM private keys, AWS key ids, and 64-hex values assigned to private_key/secret/signer names.
# (Public hashes such as genesis mixHash or tx hashes are NOT flagged.)
set -u
PATTERN="(github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|(priv(ate)?[_-]?key|secret|signer)[[:space:]\"']*[:=][[:space:]\"']*(0x)?[a-fA-F0-9]{64})"
COUNT=$(git diff --cached -U0 | grep -E '^\+[^+]' | grep -ciE "$PATTERN" || true)
if [ "${COUNT:-0}" -gt 0 ]; then
  echo "BLOCKED: $COUNT staged line(s) look like secrets (contents hidden)." >&2
  exit 1
fi
exit 0
