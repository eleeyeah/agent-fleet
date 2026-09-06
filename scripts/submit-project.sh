#!/usr/bin/env bash
# Publish a project brief to the fleet.
# Usage: submit-project.sh <project-name> <description...>
set -euo pipefail

[[ $# -ge 2 ]] || { echo "usage: $0 <project-name> <description...>" >&2; exit 1; }

NAME="$1"; shift
DESC="$*"
CORRELATION_ID="$(cat /proc/sys/kernel/random/uuid)"

BRIEF="$(jq -cn \
  --arg pid "$NAME" \
  --arg title "$NAME" \
  --arg desc "$DESC" \
  --arg cid "$CORRELATION_ID" \
  '{project_id: $pid, title: $title, description: $desc, constraints: [], correlation_id: $cid}')"

echo "Submitting brief (correlation_id=${CORRELATION_ID}):"
echo "$BRIEF" | jq .

# nats-box ships with the nats CLI; the fleet's PM listens on tasks.briefs
kubectl exec -n fleet-core deploy/nats-box -- nats pub tasks.briefs "$BRIEF"

echo "Submitted. Watch progress:"
echo "  kubectl logs -n fleet-agents deploy/pm-agent -f"
echo "  Gitea: http://192.168.178.20:30300/agents"
