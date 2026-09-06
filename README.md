# Agent Fleet

A role-based fleet of LLM agents (project manager, backend developer, reviewer) that
completes small software projects end-to-end on the local kubeadm cluster, coordinated
through git and a message queue, with **human approval gates at every merge**.

- **Phase 0** — Foundation: Gitea (in-cluster git + CI + registry), NATS JetStream
  (task queue), LiteLLM gateway (one Anthropic key, per-agent virtual keys with hard
  budgets), security baseline (namespaces, quotas, RBAC, NetworkPolicies), all deployed
  via Argo CD.
- **Phase 1** — Minimal loop: `pm-agent` decomposes a project brief into a task DAG,
  `backend-dev` implements each task on an isolated branch and opens PRs, `reviewer`
  reviews against acceptance criteria. You approve merges.

Start here: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) ·
Risks: [docs/RISKS.md](docs/RISKS.md) ·
Operations: [docs/RUNBOOK.md](docs/RUNBOOK.md) ·
Phase gates: [docs/PHASES.md](docs/PHASES.md)

## Layout

```text
agent-fleet/
  argocd/                 # App-of-Apps bootstrap (root-app -> project -> ApplicationSet)
    root-app.yaml
    project/              # AppProject + ApplicationSet (syncs envs/<env>/*)
    REPO.md               # set your git repoURL once
  envs/local/             # one Argo CD Application per component (sync-wave ordered)
    00-security/          # wave 0: namespaces, quotas, SAs, NetworkPolicies
    10-gitea/  11-nats/  12-redis/   # wave 1: core services
    13-litellm/           # wave 2: LLM gateway (needs redis + postgres)
    20-agents/            # wave 3: the fleet (Phase 1)
  manifests/              # raw k8s manifests referenced by the Applications above
    security/  redis/  agents/
  helm-values/            # values files for the Gitea / NATS / LiteLLM charts
  agents/                 # Python (LangGraph) agent implementations
    base/                 # shared container base image
    common/               # fleet_common package: task schema, NATS, Gitea, LLM, tracing
    pm/  backend-dev/  reviewer/
    templates/            # CI workflow seeded into every project repo (merge gate)
  scripts/
    bootstrap.sh          # one-time: secrets, Gitea org/bots, LiteLLM virtual keys
    submit-project.sh     # publish a project brief to the fleet
    build-images.sh       # build + push agent images to the Gitea registry
    validate.sh           # offline validation (manifests render, python compiles)
```

## Quickstart

Prerequisites: the kubeadm cluster from [`../cluster/`](../cluster/README.md), Argo CD
installed, the Patroni Postgres HA cluster from
[`../patroni-postgres-ha/`](../patroni-postgres-ha/README.md) synced (it now also
provisions the `litellm` and `agentstate` databases used here).

```bash
# 1. Push this folder to its own git repo, then set the repoURL everywhere:
#    see argocd/REPO.md

# 2. One-time bootstrap: namespaces, secrets (asks for your Anthropic key),
#    root Argo CD app, Gitea org + bot accounts, LiteLLM virtual keys w/ budgets
./scripts/bootstrap.sh

# 3. Build and push agent images to the in-cluster registry
./scripts/build-images.sh

# 4. Give the fleet a project
./scripts/submit-project.sh "todo-api" "Small FastAPI todo API with CRUD endpoints and pytest tests"

# 5. Watch: Argo CD UI, Gitea PRs (you are the merge gate), LiteLLM spend dashboard
```

## The one rule that matters

Agents never merge and never deploy. They open PRs; CI must pass; the reviewer agent
comments and approves; **a human performs every merge** (enforced by Gitea branch
protection, not by convention). Infrastructure changes only happen through Git + Argo CD.
