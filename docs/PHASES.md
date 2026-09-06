# Phases and gate criteria

A phase is done when every gate criterion passes — not before. Do not start the next
phase with a red gate.

## Phase 0 — Foundation (this repo, no agents running)

Deliverables: security baseline, Gitea, NATS, Redis, LiteLLM, Argo CD wiring,
bootstrap tooling, this documentation.

Gate:

- [ ] `argocd app list` shows `fleet-security-local`, `fleet-gitea-local`,
      `fleet-nats-local`, `fleet-redis-local`, `fleet-litellm-local` Healthy/Synced
- [ ] NetworkPolicies are **enforced** (RUNBOOK step 2 test fails to reach the internet)
- [ ] A curl through LiteLLM with an agent virtual key gets a Claude completion, and
      the spend appears against that key in the LiteLLM UI
- [ ] A key pushed over its budget is refused (test with a $0.01 throwaway key)
- [ ] A PR in a template-derived repo cannot be merged without 1 approval + green CI
- [ ] Patroni provisions `litellm` + `agentstate`; secrets copied to fleet namespaces

## Phase 1 — Minimal loop (PM + backend dev + reviewer)

Deliverables: the three agents (this repo, `agents/`), deployed as wave 3.

Gate (the proving run):

- [ ] `submit-project.sh todo-api "Small FastAPI todo API with CRUD endpoints and pytest tests"`
      produces a task DAG of 3-5 tasks (visible in pm-agent logs / KV)
- [ ] Every task lands as a PR on its own `task/<id>-a<n>` branch with green CI
- [ ] Reviewer posts a structured review on every PR before you look at it
- [ ] You merge each PR; the PM dispatches dependent tasks automatically;
      `PROJECT_DONE` appears in pm-agent logs after the last merge
- [ ] Full trace: `grep cid=<correlation_id>` across agent logs reconstructs the story;
      per-agent spend for the run is visible in LiteLLM
- [ ] Forced-failure drill: submit a brief with an impossible acceptance criterion;
      the task fails/gets rejected, retries once, then an `[escalation]` issue appears
      and the fleet stops burning tokens on it
- [ ] Budget drill: temporarily set the dev key budget to ~$0.05 and confirm the agent
      halts with budget errors instead of looping

## Phase 2 — Harden and extend (next)

- KEDA autoscaling for backend-dev on `tasks.ready` queue depth (scale-to-zero)
- Sandboxed execution: gVisor runtime class or kagent Agent Substrate for the coder
- DevOps agent: read-only cluster Role, proposes manifests via PRs only
- MCP tool servers for Gitea/cluster access; A2A between agents
- Reviewer approvals excluded from the protection quorum; re-review on push
- Escalation notifications (ntfy/email); Langfuse or OTel collector + Grafana

## Phase 3 — Scale out / AWS

- More roles (QA, frontend, docs); EKS lift (mirror `envs/eks/` like patroni);
  Bedrock as LiteLLM fallback provider; multi-project concurrency tuning.
