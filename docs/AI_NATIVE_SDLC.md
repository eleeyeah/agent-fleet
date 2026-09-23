# AI-Native Agentic Workflow — Professional Loop Design

**Status:** research / design (not implemented)  
**Primary user:** personal professional harness for internship / early developer success
(ticket → explore → plan → implement → verify → self-review → PR).  
**Scope:** Anthropic-native, short-cycle, cloud-cost-aware agentic SDLC.  
**Not in scope:** tutoring/classroom products; scaling the always-on PM/Dev/Reviewer fleet
into an employer cloud as the daily tool.

**Start here for product intent:** [intent/internship-success-loop.md](../intent/internship-success-loop.md)  
**Fleet lab lessons:** [FLEET_RETROSPECTIVE.md](FLEET_RETROSPECTIVE.md)

This note describes how the loop should work (Anthropic AI-native SDLC: an
**artifact-gated loop**, not a permanent multi-role chat swarm) and how it relates to
the existing fleet prototype.

Primary sources:

- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [The AI-Native SDLC playbook](https://claude.com/blog/the-ai-native-sdlc-playbook) (Aug 2026)
- [Claude Code best practices](https://code.claude.com/docs/en/best-practices)
- [Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview)

---

## Verdict

Build a **short-cycle, Anthropic-native agentic SDLC**:

1. **Loop, not linear pipeline** — each stage commits a versioned artifact; acceptance of that artifact triggers the next stage.
2. **Simplest agent that works** — default one coding agent with tools; add workflows (routing, evaluator–optimizer, orchestrator–workers) only when measured wins justify cost.
3. **Explore → Plan → Implement → Verify → PR** as the inner build loop (Claude Code discipline).
4. **Governance in hooks and CI**, not meetings — policy enforced as the agent acts (`CLAUDE.md`, skills, Stop hooks, branch protection).
5. **Human attention at gates**, not at every keystroke — review `intent` / `spec` / `plan` / high-risk diffs; routine work can auto-accept once rails are mature.
6. **Budgets and verifiers outside prompts** — USD / token / iteration / tool-call caps; tests and builds as ground truth.

Keep from today’s fleet: LiteLLM virtual keys, executable verifiers, attempt caps, human merge on `main`, correlation IDs.  
Change: stop treating three always-on role pods as the product; treat **artifacts + one (or few) sessions** as the product.

---

## Problem with the current fleet (for professional delivery)

| Today | Professional AI-native target |
|-------|-------------------------------|
| Roles as always-on Deployments (PM, Dev, Reviewer) | Stages as **plays** over committed artifacts; agent sessions spun per change |
| Coordination via NATS task DAG + chat-shaped prompts | Coordination via **git artifacts** (`intent.md` → `spec.md` → `plan.md` → PR) |
| Reviewer is a third LLM on every PR | Deterministic CI + optional adversarial review subagent; human for critical paths |
| Sonnet default for most calls | Route: cheap model for classify/summarize; frontier for plan/build |
| Long iteration budget (40) per task | Short cycles: small blast radius, fail/escalate early, new session for next slice |
| Fixed cluster burn (Gitea + NATS + 3 agents + …) | Scale-to-zero sessions; Managed Agents or slim harness when idle |

The fleet already got several things right (git as coordination, human merge, budgets, pytest as done). Those map cleanly onto Anthropic’s playbook. The expensive part is **topology and always-on roles**, not the gates.

---

## Anthropic principles (non-negotiable)

From *Building effective agents*:

1. **Simplest solution first** — optimize single LLM calls before multi-step; multi-step before multi-agent.
2. **Workflows vs agents** — use **workflows** (fixed code paths) when the path is known; use **agents** when step count is open-ended.
3. **Transparency** — show the plan; prefer plan mode before edits on non-trivial work.
4. **Agent–computer interface (ACI)** — invest in tool schemas the way you’d invest in UX; absolute paths, clear docs, poka-yoke.
5. **Ground truth every step** — tool results, test output, build exit codes — not self-assessment.
6. **Complexity only when it measurably helps** — multi-agent often costs ~15× tokens; coding is usually sequential.

From *Claude Code best practices*:

- Context window is the scarce resource — compact, retrieve, don’t dump.
- **Explore → Plan → Code → Commit** for non-trivial changes; skip plan for one-sentence diffs.
- Give a check the agent can run (tests, linter, build); prefer Stop hooks / goals for unattended runs.
- Adversarial review in a **fresh** subagent context before calling work done.
- Encode institutional knowledge in `CLAUDE.md` + skills, not tribal memory.

From *AI-Native SDLC playbook*:

- Code is no longer the bottleneck; **plan / review / deploy** must be redesigned or gains stall.
- Each stage ends by **committing an artifact**; the next stage starts by reading it.
- Humans stay accountable; attention moves to **gates**, not every line.
- Start instrumenting **Build + Deploy** first (fast feedback: plan-compliance, first-pass merge rate).

---

## Target loop: short AI-native cycle

```text
                    ┌─────────────────────────────────────┐
                    │         continuous maintain         │
                    │  (control-band breach → new intent) │
                    └──────────────────▲──────────────────┘
                                       │
intent.md ─► spec.md ─► plan.md ─► build+tests ─► PR+review ─► merge/deploy
   ▲              │          │            │             │
   │              │          │            │             │
 human gate    human gate  human gate   verifier     human / policy
 (PO accept)   (PO/eng)    (eng signoff) (CI/hooks)   (critical paths)
```

### Outer cycle (delivery) — artifact chain

| Stage | Artifact | Agent role | Human gate |
|-------|----------|------------|------------|
| Plan | `intent.md` | Synthesize problem, outcome, constraints | Product owner accept/reject |
| Design | `spec.md` | Requirements + design under org skills | Owner/eng accept |
| Build | `plan.md` then diff | Plan mode → implement (bounded) | Eng approves plan before auto-apply on risky work |
| Test | CI evidence | Run tests/evals continuously while building | Fail = stop, don’t merge |
| Deploy | PR + review findings | Agentic review layers; hooks as policy | Human for regulated / high-blast-radius |
| Maintain | incident → new `intent.md` | Diagnose within gated routes | Triage, don’t hand-write every ticket |

### Inner cycle (build session) — Claude Code shape

1. **Explore** (read-only) — map files, constraints, existing patterns.
2. **Plan** — write `plan.md` (files, order, risks); wait for approval when blast radius > trivial.
3. **Implement** — small diffs; follow repo patterns; write/adjust tests with the change.
4. **Verify** — run the real check; iterate until green or hit budget → escalate.
5. **Review** — fresh-context adversarial pass against `plan.md` / acceptance criteria.
6. **Ship** — commit, open PR; merge only via existing human/policy gate.

**Short cycle rules (hard):**

| Rule | Guideline |
|------|-----------|
| Blast radius | Prefer one vertical slice / one PR; avoid multi-day agent runs without intermediate commits |
| Session length | New session when context is fat or goal changes; don’t stretch one conversation across unrelated intents |
| Iteration cap | Start ~8–12 tool-heavy turns per slice; escalate rather than grind |
| Same failure | ≤2–3 identical failures → stop and open escalation with evidence |
| Parallelism | ≤2 implementers; only on non-overlapping ownership (worktrees) |
| Model | Haiku/small for route, summarize, checklist; Sonnet/Opus for plan + multi-file build |
| Done | Verifier green + plan compliance — never “looks good” |

---

## Architecture (chosen): Claude Code + Jev

**Locked for the internship-success track** — see [IMPLEMENTATION_CLAUDE_CODE_JEV.md](IMPLEMENTATION_CLAUDE_CODE_JEV.md).

| Layer | Choice | Role |
|-------|--------|------|
| Generate / act | Claude Code | Explore, plan, edit, verify commands, PR draft |
| Decide / gate | Jev (TypeSafe AI System One) | Choice / Score / Noul: route play, complexity, ambiguity, tool risk, loop detect, ready-for-PR |
| Done signal | Deterministic verifier | Tests / lint / build exit codes — never Jev alone |
| Human gate | Mentor / you | Plan accept on risky work; real PR approval |

Earlier options (Managed Agents-only, Messages API thin harness, hybrid) remain **later** evolution paths. Daily path does **not** use always-on PM/Reviewer pods.

Retain Gitea/NATS only as the overnight fleet lab SKU. Personal loop needs git + Claude Code + Jev helper + CI.

---

## How fleet roles map (and shrink)

| Fleet role | AI-native equivalent | Cost posture |
|------------|----------------------|--------------|
| `pm-agent` | Workflow: `intent` → `spec` → task slices (often one model call + validation graph) | Not a 24/7 pod; run on demand |
| `backend-dev` | Single build agent / Managed Agent session | Core spend; keep bounded |
| `reviewer` | CI + optional review subagent in fresh context; human for critical | Don’t pay a third Sonnet on every trivial PR |

Role separation remains valuable as **constraints** (builder shouldn’t approve merge). Enforce with permissions and hooks, not three always-warm LLM services.

---

## Engineering guidelines (working agreements)

### Design

- Prefer **workflows** for Plan/Design (structured outputs, schemas, validation).
- Prefer **one agent** for Build unless subtasks are proven independent.
- Encode policy in `CLAUDE.md` + skills + hooks before adding another agent.
- Spec and plan are code — versioned, reviewed, diffable.

### Build

- Plan mode before non-trivial edits.
- Tests co-generated with code; CI is the merge gate.
- Truncate tool output; retrieve symbols/files on demand.
- Absolute paths and narrow tools (good ACI).

### Test / Deploy

- Deterministic gates first; LLM review second.
- Hooks block unsafe actions at tool time (budget, path scope, secret-like writes).
- Human merge retained for `main` until policy maturity justifies tighter automation.

### Operate / Cost

- Per-project or per-team LiteLLM virtual keys with hard daily USD caps.
- Receipts per run: tokens, model, stop reason, verifier evidence, artifact SHAs.
- Measure: time intent→merged PR, first-pass CI green rate, $/merged PR, escape defects.

### SDLC / Maintainability

- TDD where the domain allows: failing test → implement → green.
- Small PRs, clear boundaries (SOLID at module edges the agent is allowed to touch).
- Event-driven outer loop: artifact accept / CI fail / prod breach → next play (EDA at the process layer).
- Clean architecture for the harness: domain (artifacts, budgets) separate from providers (Anthropic, git, CI).

---

## Phased adoption (short cycles of the platform itself)

### Cycle 1 — Artifact contract + single build agent

- Templates: `intent.md`, `spec.md`, `plan.md`.
- One agent session: explore → plan → implement → pytest → PR.
- LiteLLM budgets; iteration/tool caps; human merge unchanged.
- **Exit:** one real feature merges under published $/PR and cycle-time baselines.

### Cycle 2 — Hooks, CLAUDE.md, adversarial review

- Repo `CLAUDE.md` + skills for stack conventions.
- Stop hook / verifier gate; fresh-context review against `plan.md`.
- Eval harness for plan-compliance and first-pass merge rate.

### Cycle 3 — Outer SDLC automation

- Accepted `intent` triggers design workflow; approved `spec` triggers build job.
- Optional Managed Agents for long unattended slices.
- Maintain path: alert → draft `intent.md` (human triage).

### Cycle 4 — Selective multi-agent

- Only for breadth-first or true parallel ownership.
- Concurrency cap; shared verifier; same budget hooks.
- Keep overnight “fleet” mode as a SKU if still needed — not the default interactive path.

---

## Decision checklist (before adding agents or infra)

1. Can a workflow (fixed steps + schema validation) do this cheaper than an agent?
2. Can one agent with better tools/`CLAUDE.md` do this without a second model?
3. Is there a deterministic verifier, or are we grading ourselves?
4. Is the change small enough for a short cycle, or should we split the intent?
5. Will the quality gain beat the token/ops cost on a measured eval?

If any answer is weak → do not add a pod, a queue, or a specialist LLM.

---

## Relation to this repository

| Keep | Evolve | Defer / drop for default path |
|------|--------|-------------------------------|
| LiteLLM + virtual keys + budgets | Replace role Deployments with session runner + artifact plays | Always-on PM + Reviewer for every change |
| Pytest / CI as done | Add plan mode + `plan.md` gate | NATS as primary UX (keep as optional job bus) |
| Human merge on `main` | Hooks for policy-as-code | More permanent roles before Build/Deploy metrics improve |
| Correlation IDs / spend UI | Receipts tied to artifact SHAs | Unbounded iteration |

**Product intent:** [intent/internship-success-loop.md](../intent/internship-success-loop.md)  
**Lab lessons:** [FLEET_RETROSPECTIVE.md](FLEET_RETROSPECTIVE.md)

---

## Sources

- Anthropic — [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- Anthropic — [AI-Native SDLC playbook](https://claude.com/blog/the-ai-native-sdlc-playbook)
- Anthropic — [Claude Code best practices](https://code.claude.com/docs/en/best-practices)
- Anthropic — [Claude Managed Agents overview](https://platform.claude.com/docs/en/managed-agents/overview)
- Supporting cost/loop practice: [loop engineering](https://futureagi.com/blog/loop-engineering/how-to-do-loop-engineering/), [MartinLoop](https://github.com/Keesan12/martin-loop/), topology cost notes (~15× multi-agent tax)
