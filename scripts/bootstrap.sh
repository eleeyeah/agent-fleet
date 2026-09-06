#!/usr/bin/env bash
# One-time (idempotent) bootstrap for the agent fleet.
#
# What it does, in order:
#   1. Namespaces (so secrets can exist before Argo CD syncs)
#   2. Secrets that must never be in git:
#        - Anthropic API key (prompted or $ANTHROPIC_API_KEY)   -> fleet-core
#        - LiteLLM master key (generated)                       -> fleet-core
#        - Gitea admin credentials (generated)                  -> fleet-git
#        - Gitea webhook secret (generated)                     -> fleet-git + fleet-agents
#        - Patroni db credentials copied from postgres-ha       -> fleet-core / fleet-agents
#   3. Applies argocd/root-app.yaml and waits for Gitea + LiteLLM
#   4. Gitea: org, bot users + tokens, template repo, org webhook -> reviewer
#   5. LiteLLM: one virtual key per agent with HARD budget caps (risk #2)
#
# Requirements: kubectl (context = the homelab cluster), jq, curl, openssl.
# The Patroni cluster from ../patroni-postgres-ha must be synced first (it
# provisions the litellm/agentstate databases).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# ---------------------------------------------------------------- configuration
GITEA_ORG="agents"
GITEA_ADMIN_USER="fleet-admin"
BOTS=(pm-bot dev-bot review-bot)
# Daily budgets in USD per agent virtual key — the hard stop for runaway spend.
BUDGET_PM="5"
BUDGET_DEV="10"
BUDGET_REVIEW="5"
PG_SVC="acid-postgres-cluster"
PG_NS="postgres-ha"

log()  { printf '\033[1;32m[bootstrap]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[bootstrap]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[bootstrap]\033[0m %s\n' "$*" >&2; exit 1; }

for bin in kubectl jq curl openssl; do
  command -v "$bin" >/dev/null || die "missing required tool: $bin"
done
kubectl cluster-info >/dev/null 2>&1 || die "kubectl cannot reach the cluster"

# Create a secret only if it does not exist (idempotency guard).
ensure_secret() {
  local ns="$1" name="$2"; shift 2
  if kubectl get secret -n "$ns" "$name" >/dev/null 2>&1; then
    log "secret $ns/$name exists — keeping"
  else
    kubectl create secret generic -n "$ns" "$name" "$@"
    log "created secret $ns/$name"
  fi
}

secret_val() { # ns name key
  kubectl get secret -n "$1" "$2" -o jsonpath="{.data.$3}" | base64 -d
}

# ------------------------------------------------------------- 1. namespaces
log "applying namespaces"
kubectl apply -f "$ROOT_DIR/manifests/security/namespaces.yaml"

# ---------------------------------------------------------------- 2. secrets
if ! kubectl get secret -n fleet-core litellm-env-secret >/dev/null 2>&1; then
  if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    read -rs -p "Anthropic API key (input hidden): " ANTHROPIC_API_KEY; echo
  fi
  [[ -n "$ANTHROPIC_API_KEY" ]] || die "no Anthropic API key provided"
  kubectl create secret generic -n fleet-core litellm-env-secret \
    --from-literal=ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY"
  log "created secret fleet-core/litellm-env-secret"
fi

ensure_secret fleet-core litellm-master-key \
  --from-literal=masterkey="sk-fleet-$(openssl rand -hex 24)"

ensure_secret fleet-git gitea-admin-secret \
  --from-literal=username="$GITEA_ADMIN_USER" \
  --from-literal=password="$(openssl rand -base64 24 | tr -d '/+=')" \
  --from-literal=email="fleet-admin@fleet.local"

WEBHOOK_SECRET_EXISTING=""
if kubectl get secret -n fleet-agents gitea-webhook-secret >/dev/null 2>&1; then
  WEBHOOK_SECRET_EXISTING="$(secret_val fleet-agents gitea-webhook-secret secret)"
fi
WEBHOOK_SECRET="${WEBHOOK_SECRET_EXISTING:-$(openssl rand -hex 24)}"
ensure_secret fleet-agents gitea-webhook-secret --from-literal=secret="$WEBHOOK_SECRET"

# Patroni credentials (created by the Zalando operator once patroni-postgres-ha syncs
# with the litellm/agent_fleet users from its values.yaml)
copy_pg_credentials() { # pg_user target_ns target_name db_name
  local pg_user="$1" tns="$2" tname="$3" db="$4"
  # Zalando normalizes underscores to hyphens in secret names (agent_fleet -> agent-fleet)
  local src="${pg_user//_/-}.${PG_SVC}.credentials.postgresql.acid.zalan.do"
  kubectl get secret -n "$PG_NS" "$src" >/dev/null 2>&1 \
    || die "Patroni secret $PG_NS/$src not found — sync patroni-postgres-ha first (it now declares the '$pg_user' user)"
  local user pass user_enc pass_enc uri
  user="$(secret_val "$PG_NS" "$src" username)"
  pass="$(secret_val "$PG_NS" "$src" password)"
  user_enc="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$user")"
  pass_enc="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$pass")"
  uri="postgresql://${user_enc}:${pass_enc}@${PG_SVC}.${PG_NS}.svc.cluster.local:5432/${db}?sslmode=disable"
  # Always refresh: Zalando passwords often contain URL-special characters, and the
  # first copy may have built a broken uri (LiteLLM migrations then crash-loop).
  kubectl create secret generic -n "$tns" "$tname" \
    --from-literal=username="$user" \
    --from-literal=password="$pass" \
    --from-literal=uri="$uri" \
    --dry-run=client -o yaml | kubectl apply -f -
  log "upserted secret $tns/$tname"
}
copy_pg_credentials litellm fleet-core litellm-db-credentials litellm
copy_pg_credentials agent_fleet fleet-agents agent-checkpoint-db agentstate

# --------------------------------------------------- 3. root app + wait for core
log "applying Argo CD root app"
kubectl apply -f "$ROOT_DIR/argocd/root-app.yaml"

wait_for_deploy() { # ns name timeout_s
  local ns="$1" name="$2" timeout="$3" i
  log "waiting for deploy/${name} in ${ns} (up to ${timeout}s — Argo CD must sync first)"
  for ((i=0; i<timeout; i+=10)); do
    if kubectl get deploy -n "$ns" "$name" >/dev/null 2>&1; then
      kubectl rollout status -n "$ns" "deploy/${name}" --timeout="${timeout}s" && return 0
    fi
    sleep 10
  done
  return 1
}

wait_for_deploy fleet-git gitea 600 \
  || die "Gitea did not become ready. In Argo CD, open fleet-gitea-local and read ComparisonError."
wait_for_deploy fleet-core litellm 600 \
  || warn "LiteLLM not ready yet — virtual key step may fail; re-run bootstrap after it settles"

# ------------------------------------------------------------- 4. Gitea setup
GITEA_LOCAL_PORT=3999
kubectl port-forward -n fleet-git svc/gitea-http "${GITEA_LOCAL_PORT}:3000" >/dev/null 2>&1 &
PF_GITEA=$!
LITELLM_LOCAL_PORT=4999
kubectl port-forward -n fleet-core svc/litellm "${LITELLM_LOCAL_PORT}:4000" >/dev/null 2>&1 &
PF_LITELLM=$!
trap 'kill $PF_GITEA $PF_LITELLM 2>/dev/null || true' EXIT
sleep 3

GITEA="http://127.0.0.1:${GITEA_LOCAL_PORT}"
ADMIN_PASS="$(secret_val fleet-git gitea-admin-secret password)"
AUTH=(-u "${GITEA_ADMIN_USER}:${ADMIN_PASS}")

gitea_api() { # method path [json]
  local method="$1" path="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -sf "${AUTH[@]}" -X "$method" -H 'Content-Type: application/json' \
      -d "$body" "${GITEA}/api/v1${path}"
  else
    curl -sf "${AUTH[@]}" -X "$method" "${GITEA}/api/v1${path}"
  fi
}

log "creating Gitea org '$GITEA_ORG'"
gitea_api GET "/orgs/${GITEA_ORG}" >/dev/null 2>&1 \
  || gitea_api POST /orgs "{\"username\":\"${GITEA_ORG}\",\"visibility\":\"private\"}" >/dev/null

for bot in "${BOTS[@]}"; do
  if ! gitea_api GET "/users/${bot}" >/dev/null 2>&1; then
    log "creating bot user $bot"
    gitea_api POST /admin/users "{
      \"username\": \"${bot}\",
      \"email\": \"${bot}@fleet.local\",
      \"password\": \"$(openssl rand -base64 24 | tr -d '/+=')\",
      \"must_change_password\": false
    }" >/dev/null
    # Org membership: owners team so pm-bot can create repos; dev/review get repo
    # access via the same team for Phase 1 simplicity (tighten in Phase 2).
    OWNERS_TEAM_ID="$(gitea_api GET "/orgs/${GITEA_ORG}/teams/search?q=Owners" | jq '.data[0].id')"
    gitea_api PUT "/teams/${OWNERS_TEAM_ID}/members/${bot}" >/dev/null
  fi
  if ! kubectl get secret -n fleet-agents "${bot}-token" >/dev/null 2>&1; then
    log "issuing API token for $bot"
    TOKEN_JSON="$(curl -sf "${AUTH[@]}" -X POST -H 'Content-Type: application/json' \
      -H "Sudo: ${bot}" \
      -d "{\"name\":\"fleet-$(date +%s)\",\"scopes\":[\"write:repository\",\"write:issue\",\"write:organization\",\"write:package\",\"write:user\"]}" \
      "${GITEA}/api/v1/users/${bot}/tokens")"
    BOT_TOKEN="$(echo "$TOKEN_JSON" | jq -r .sha1)"
    kubectl create secret generic -n fleet-agents "${bot}-token" \
      --from-literal=username="$bot" --from-literal=token="$BOT_TOKEN"
    log "created secret fleet-agents/${bot}-token"
  fi
done

log "ensuring template repo '${GITEA_ORG}/project-template'"
if ! gitea_api GET "/repos/${GITEA_ORG}/project-template" >/dev/null 2>&1; then
  gitea_api POST "/orgs/${GITEA_ORG}/repos" '{
    "name": "project-template",
    "private": true,
    "auto_init": true,
    "default_branch": "main",
    "template": true
  }' >/dev/null
  # Seed the CI workflow (the automated merge gate, risk #7)
  CI_B64="$(base64 -w0 "$ROOT_DIR/agents/templates/project-ci.yaml")"
  gitea_api POST "/repos/${GITEA_ORG}/project-template/contents/.gitea/workflows/ci.yaml" \
    "{\"content\":\"${CI_B64}\",\"message\":\"ci: test gate\"}" >/dev/null
  log "seeded CI workflow into template repo"
fi

log "ensuring org webhook -> reviewer agent"
HOOK_TARGET="http://reviewer-agent.fleet-agents.svc.cluster.local:8080/webhook/gitea"
EXISTING_HOOK="$(gitea_api GET "/orgs/${GITEA_ORG}/hooks" | jq --arg u "$HOOK_TARGET" '[.[] | select(.config.url == $u)] | length')"
if [[ "$EXISTING_HOOK" == "0" ]]; then
  gitea_api POST "/orgs/${GITEA_ORG}/hooks" "{
    \"type\": \"gitea\",
    \"active\": true,
    \"events\": [\"pull_request\", \"pull_request_sync\", \"pull_request_closed\"],
    \"config\": {
      \"url\": \"${HOOK_TARGET}\",
      \"content_type\": \"json\",
      \"secret\": \"${WEBHOOK_SECRET}\"
    }
  }" >/dev/null
  log "org webhook created"
fi

# ------------------------------------------------- 5. LiteLLM virtual keys
MASTER_KEY="$(secret_val fleet-core litellm-master-key masterkey)"
LITELLM="http://127.0.0.1:${LITELLM_LOCAL_PORT}"

make_virtual_key() { # agent budget_usd_per_day
  local agent="$1" budget="$2" secret="${1}-litellm-key"
  if kubectl get secret -n fleet-agents "$secret" >/dev/null 2>&1; then
    log "secret fleet-agents/$secret exists — keeping"
    return
  fi
  log "generating LiteLLM virtual key for $agent (max \$${budget}/day)"
  KEY_JSON="$(curl -sf -X POST "${LITELLM}/key/generate" \
    -H "Authorization: Bearer ${MASTER_KEY}" \
    -H 'Content-Type: application/json' \
    -d "{
      \"key_alias\": \"${agent}\",
      \"models\": [\"claude-sonnet\", \"claude-haiku\"],
      \"max_budget\": ${budget},
      \"budget_duration\": \"1d\",
      \"rpm_limit\": 60,
      \"metadata\": {\"fleet_agent\": \"${agent}\"}
    }")" || { warn "LiteLLM key generation failed for $agent — is LiteLLM ready? Re-run bootstrap."; return 1; }
  VKEY="$(echo "$KEY_JSON" | jq -r .key)"
  kubectl create secret generic -n fleet-agents "$secret" --from-literal=api_key="$VKEY"
  log "created secret fleet-agents/$secret"
}
make_virtual_key pm-agent "$BUDGET_PM"
make_virtual_key backend-dev-agent "$BUDGET_DEV"
make_virtual_key reviewer-agent "$BUDGET_REVIEW"

log "bootstrap complete"
cat <<EOF

Next steps:
  1. ./scripts/build-images.sh            # build + push agent images
  2. Argo CD syncs 20-agents (wave 3)     # fleet comes up
  3. ./scripts/submit-project.sh todo-api "Small FastAPI todo API with tests"
  Gitea UI:    http://192.168.178.20:30300  (user: ${GITEA_ADMIN_USER})
  LiteLLM UI:  kubectl port-forward -n fleet-core svc/litellm 4000:4000 -> http://127.0.0.1:4000/ui
EOF
