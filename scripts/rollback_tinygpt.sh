#!/usr/bin/env bash
# Roll the live TinyGPT checkpoint back to the previous promoted one.
#
# The retrain orchestrator (scripts/retrain_tinygpt.py) copies the outgoing
# live checkpoint to <data>/tinygpt.pt.prev BEFORE it promotes a new one. So a
# regression that slipped past the gate can be undone by restoring .prev.
#
# Serve is NOT affected unless config/settings.json has "model": "tinygpt"
# (default is "auto" -> Markov, which never reads this file). If it does, a
# restart is needed for the swap to take effect:
#   kill $(systemctl show shaggoth -p MainPID --value)
set -euo pipefail
DATA="${1:-/home/matt/Shaggoth-a1/data}"
LIVE="$DATA/tinygpt.pt"
PREV="$DATA/tinygpt.pt.prev"

if [ ! -f "$PREV" ]; then
  echo "No previous checkpoint at $PREV -- nothing to roll back to." >&2
  echo "(Nothing has been promoted yet, or only one checkpoint has ever existed.)" >&2
  exit 1
fi

for ext in "" ".tok.json" ".json"; do
  if [ -f "$PREV$ext" ]; then
    cp -p "$PREV$ext" "$LIVE$ext"
    echo "restored $LIVE$ext  <-  $PREV$ext"
  fi
done
echo "Rolled back to the previous checkpoint."
echo "If serve uses model=tinygpt, restart it: kill \$(systemctl show shaggoth -p MainPID --value)"
