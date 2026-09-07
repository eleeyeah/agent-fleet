#!/usr/bin/env bash
# Build the agent images and push them to the in-cluster Gitea OCI registry.
# Requires: docker, and containerd on every node configured to trust the
# insecure registry (see docs/RUNBOOK.md).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS_DIR="$(dirname "$SCRIPT_DIR")/agents"

REGISTRY="${REGISTRY:-192.168.178.20:30300}"
ORG="${ORG:-agents}"
TAG="${TAG:-0.1.0}"

# Registry auth: dev-bot has write:package. Pull creds from the cluster secret
# unless GITEA_USER/GITEA_TOKEN are provided.
if [[ -z "${GITEA_TOKEN:-}" ]]; then
  GITEA_USER="$(kubectl get secret -n fleet-agents dev-bot-token -o jsonpath='{.data.username}' | base64 -d)"
  GITEA_TOKEN="$(kubectl get secret -n fleet-agents dev-bot-token -o jsonpath='{.data.token}' | base64 -d)"
fi
# Gitea advertises ROOT_URL as the OCI token realm. That must be the NodePort
# (http://192.168.178.20:30300/), not in-cluster DNS — docker and kubelet run
# on the host and cannot resolve *.svc.cluster.local.
echo "$GITEA_TOKEN" | docker login "$REGISTRY" -u "$GITEA_USER" --password-stdin

# Kubelet pull of a private Gitea package needs this on the agent ServiceAccounts.
kubectl create secret docker-registry gitea-registry -n fleet-agents \
  --docker-server="$REGISTRY" \
  --docker-username="$GITEA_USER" \
  --docker-password="$GITEA_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> base image"
docker build -t fleet-base:"$TAG" -f "$AGENTS_DIR/base/Dockerfile" "$AGENTS_DIR"

for agent in pm backend-dev reviewer; do
  echo "==> $agent"
  docker build \
    --build-arg BASE_IMAGE="fleet-base:$TAG" \
    -t "$REGISTRY/$ORG/fleet-$agent:$TAG" \
    -f "$AGENTS_DIR/$agent/Dockerfile" "$AGENTS_DIR"
  docker push "$REGISTRY/$ORG/fleet-$agent:$TAG"
done

echo "Pushed: $REGISTRY/$ORG/fleet-{pm,backend-dev,reviewer}:$TAG"
echo "If you bumped TAG, update manifests/agents/*.yaml image tags (GitOps!)"
