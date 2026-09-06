# Risk register

Every risk is mapped to the artifact that implements its mitigation. If you change
one of these files, re-check the risk it guards.

| # | Risk | Mitigation | Implemented in |
|---|------|------------|----------------|
| 1 | An agent damages the cluster (worst case: future DevOps agent) | No agent has Kubernetes API access at all in Phase 1: per-agent ServiceAccounts with `automountServiceAccountToken: false`, no Roles bound. Infra changes only via Git PR -> Argo CD. | `manifests/security/serviceaccounts.yaml`, Deployments in `manifests/agents/` |
| 2 | Runaway token spend (looping agent drains the budget) | Hard daily budget + RPM limit per virtual key; requests stop at the cap. Iteration bound per task (`recursion_limit`), attempt bound per task, decomposition size bound. | `scripts/bootstrap.sh` (make_virtual_key), `fleet_common/config.py`, `backend-dev/app/coder.py` |
| 3 | Agents overwrite each other's work | One fresh clone + branch per task attempt (`task/<id>-a<n>`); the TASKS stream is a work queue (each task consumed exactly once); merges only through PRs. | `backend-dev/app/main.py`, `fleet_common/bus.py` |
| 4 | Agent-generated code does something malicious/destructive in-pod | Restricted Pod Security Standard (non-root, no privilege escalation, seccomp, dropped capabilities); path-escape guard on file tools; command timeouts; ephemeral size-limited workspace; **no internet egress** — only LiteLLM, NATS, Gitea, Postgres, DNS. Reviewer auto-rejects any diff touching CI workflows. | `manifests/security/namespaces.yaml` (PSS), `networkpolicies.yaml`, `coder.py`, `reviewer/app/review.py` |
| 5 | Leaked API key | Real Anthropic key exists in exactly one Secret mounted by LiteLLM. Agents carry revocable virtual keys; blast radius = one agent's daily budget. Bot git tokens are per-agent and revocable. | `helm-values/litellm.yaml`, `scripts/bootstrap.sh` |
| 6 | Silent failure / undebuggable behavior | correlation_id propagated brief -> tasks -> events -> logs -> PR bodies -> escalation issues; structured logs; optional OTLP tracing; LiteLLM spend/log dashboard per key. | `fleet_common/tracing.py`, `fleet_common/models.py` |
| 7 | Bad code merged or deployed autonomously | Branch protection on `main`: push blocked, 1 approval + green CI required, human performs every merge. CI (pytest) seeded into every repo from the template. Deploys happen only when a human-merged commit syncs via Argo CD. | `fleet_common/gitea.py` (protect_main), `agents/templates/project-ci.yaml`, `scripts/bootstrap.sh` |
| 8 | Resource exhaustion on laptop-class nodes | ResourceQuota + LimitRange in every fleet namespace; explicit requests/limits on every pod; `emptyDir` size limits; single-task-at-a-time dev agent in Phase 1. | `manifests/security/quotas.yaml`, `manifests/agents/*.yaml` |

## Known gaps (accepted for Phase 1, revisit in Phase 2)

- **NetworkPolicy enforcement requires replacing/augmenting Flannel** with Calico or
  Cilium. Until then risk #4's network mitigation is declared but inactive
  (RUNBOOK has the procedure).
- **No syscall-level sandbox** (gVisor / kagent Agent Substrate) around
  agent-executed code yet.
- **Reviewer approval counts in Gitea's approval quorum** — the human gate currently
  relies on bots having no merge permission and on you doing the merge. Phase 2:
  dedicated review team whose approvals don't satisfy protection, or required
  approvals = 2.
- **Escalation notification** is a Gitea issue only; add ntfy/email in Phase 2 if
  you don't check the UI regularly.
