# Companion Agentic Loop — Research & Target Architecture

**Status:** research / design (not implemented)  
**Product intent:** a cloud companion for *learning* and *producing* software — not an autonomous multi-role engineering fleet.  
**Problem with the current fleet:** Phase 1 (`pm` + `backend-dev` + `reviewer` + Gitea + NATS + LiteLLM + Redis + Postgres) is the right shape for *hands-off project completion*, but it is the wrong cost shape for a always-on learning companion.

This note captures external research (2024–2026) and maps it onto what we already built, so the next product can reuse the good rails and drop the expensive topology.

---

## Verdict

For a learning + coding companion, default to a **single ReAct agent** with:

1. **Deterministic outer loop** (not LLM-orchestrated multi-agent chat)
2. **Role-as-skills / prompts**, not role-as-always-running pods
3. **Cheap model routing** (Haiku for classify / hint / quiz; Sonnet only for hard code edits)
4. **Hard budgets outside the prompt** (iteration, tool-call, token, USD caps)
5. **Executable gates** (tests, linters, quizzes) as ground truth — never the model's self-assessment
6. **Learner state** (mastery, misconceptions, session history) as durable memory — not three agent contexts talking to each other

Keep the fleet's **gates** (budgets, human merge, CI, correlation IDs, LiteLLM virtual keys). Drop the fleet's **always-on multi-agent topology** for the companion product.

Anthropic's rule still applies: *[find the simplest solution, increase complexity only when it measurably helps](https://www.anthropic.com/engineering/building-effective-agents)*. Multi-agent systems often use on the order of **~15× more tokens** than chat; coding work is usually sequential, so that tax rarely pays for itself.

---

## Why the current fleet is expensive (cost anatomy)

| Cost driver | What we do today | Why it hurts in cloud companion mode |
|-------------|------------------|--------------------------------------|
| Topology | 3 specialized agents per project turn | Each turn pays PM decompose + Dev ReAct + Reviewer LLM; coordination tax compounds |
| Context duplication | Each agent loads its own system prompt + task + repo slice | Same facts re-sent 3×; prefix cache rarely shared across services |
| Always-on infra | Gitea, NATS, Redis, LiteLLM, 3 Deployments, Postgres DBs | Fixed cloud burn even when the user is idle / asking a quiz question |
| Sonnet default | `FLEET_MODEL=claude-sonnet` for coding (and typically review) | Fine for hard edits; wasteful for explain / hint / classify / route |
| Unbounded feel | `max_iterations=40` per task | Good safety rail exists, but one stuck task still burns a large slice of the daily budget |
| Parallel ambition (Phase 2+) | KEDA scale-out, more roles | Parallel agents multiply spend; research warns concurrency caps (often ≤2) matter more than more roles |

What is already *correct* and should survive into the companion:

- LiteLLM virtual keys with hard daily budgets
- Executable done-condition (`pytest` / verifier), not “I fixed it”
- Attempt / escalation limits before infinite retry
- Human gate for anything that lands on `main`
- Correlation IDs and spend visibility

---

## Research synthesis (what “best” looks like in 2026)

### 1. Pick topology by work shape, not by fashion

From [three topologies: single / supervisor / swarm](https://cutler.sg/blog/2026-05-three-topologies-single-agent-supervisor-swarm) and Anthropic:

| Topology | Fit | Token posture |
|----------|-----|---------------|
| **Single ReAct** | Everyday coding, tutoring, debug, explain-this-file | Cheapest; default |
| **Supervisor + workers** | Breadth-first independent subproblems (audit many files, research) | ~15× chats; only when independence is real |
| **Swarm on rails** | Homogeneous batch work with hard CI gates | Needs sandbox + cron + veto; not a tutor UX |

A companion is interactive and sequential → **single agent**.

### 2. The loop that stops (and therefore stays cheap)

Consensus across [loop engineering](https://futureagi.com/blog/loop-engineering/how-to-do-loop-engineering/), [MartinLoop](https://github.com/Keesan12/martin-loop/), and [safe coding loops](https://www.verdent.ai/guides/tutorial/build-coding-agent-loop):

Every run needs an explicit **contract**:

- Objective (what “done” means)
- Verifier (real command / quiz / rubric — not self-report)
- Budget (USD / tokens / iterations / tool calls)
- Scope (allowed paths / tools)
- Stop + escalate rules (identical failure twice → human / cheaper fallback)

**Budget lives in hooks / gateway code, not in the system prompt.** Prompts do not stop runaway spend; LiteLLM caps and loop counters do (we already practice this).

Suggested companion defaults (stricter than fleet Phase 1):

| Cap | Suggested starting value | Rationale |
|-----|--------------------------|-----------|
| Tool calls / turn | 15 (code), 5 (research/explain) | Stops silent retry burn |
| Iterations / task | 8–12 | Fleet uses 40; companion should escalate sooner |
| Same-failure retries | 2–3 | Then escalate or switch strategy |
| Concurrent coding workers | 0–1 (max 2 later) | Parallelism is a spend multiplier |
| Daily USD / user | product policy via LiteLLM key | Hard stop overnight |

### 3. Cost levers that actually move the bill

Empirical work on multi-turn coding agents ([context compression gateways](https://arxiv.org/abs/2609.22114); [Copilot token efficiency](https://github.blog/ai-and-ml/github-copilot/getting-more-from-each-token-how-copilot-improves-context-handling-and-model-routing/)):

1. **Tool-schema filtering** — only send tools relevant to this turn (large fixed saving every turn).
2. **Targeted retrieval** — repo map / RAG / AST chunks instead of stuffing files (~order-of-magnitude input reduction in RAG coding assistants).
3. **History compaction** — summarize old turns; keep recent tool results short (we already truncate tool output at 8k chars in `coder.py`).
4. **Model routing with cache awareness** — Haiku for route/hint/quiz; Sonnet for multi-file edits; avoid bouncing models mid-session when prefix cache is warm.
5. **Skills over always-loaded MCP** — load pedagogical / tooling skills on demand (reported large token cuts vs loading every tool schema).

### 4. Learning companion specifics

Product-shaped patterns that beat “three coding agents chatting”:

- **Centralized learner state** (mastery, misconceptions, review schedule) with a single writer — see IntelliCode-style designs — so “specialists” can be pure functions / skills over shared state, not separate LLM fleets.
- **Socratic / graduated hints** before full solutions (fewer long code-generation turns).
- **Codebase-grounded tutoring** with file:symbol anchors and a hard exploration budget (e.g. ≤10 file reads before teaching).
- **Mode switch in one agent**: `tutor` | `pair` | `implement` | `review` — same process, different system prompt + tool allowlist + model tier.

Multi-agent tutoring demos exist, but their win is usually **stateful pedagogy**, not parallel LLM workers. Implement the state machine in code; call the LLM only where variance helps (hints, explanations, edits).

---

## Target architecture: Companion Loop v1

```text
User
  │
  ▼
API / session gateway
  │  - auth, rate limit, per-user LiteLLM virtual key
  │  - mode: tutor | pair | implement
  ▼
Router (Haiku, structured) ──► cheap path: FAQ / quiz / explain (1–2 calls)
  │
  ▼ (only if tools / code needed)
Single Companion Agent (ReAct)
  tools: read/search/edit/run_tests/run_quiz  (filtered schema)
  memory: learner_state + session_summary + retrieved chunks
  caps: iterations, tool calls, USD
  │
  ▼
Verifier gate (deterministic)
  - pytest / linter / quiz rubric
  │
  ▼
Persist: learner_state, receipt (tokens, stop reason, verifier evidence)
```

### What we keep from agent-fleet

| Fleet asset | Companion reuse |
|-------------|-----------------|
| LiteLLM + virtual keys + budgets | Per-user or per-mode keys; same gateway |
| `fleet_common` bounds / tracing ideas | Port as `companion_common` |
| Executable verifier mindset | Core of the loop |
| Human merge for shared repos | Optional “ship” mode later |
| Restricted PSS / no egress except gateway | Sandbox for `run_command` |

### What we do **not** carry into companion v1

| Fleet piece | Why drop / defer |
|-------------|------------------|
| Always-on `pm-agent` + `reviewer-agent` pods | Roles become prompts/skills invoked on demand |
| NATS task DAG for every user message | Overkill for interactive chat; use session state + optional job queue later |
| Full in-cluster Gitea for every lesson | Use the learner's repo (GitHub/local) or a lightweight workspace; Gitea fleet stays for autonomous project mode if we keep it |
| LangGraph multi-agent graphs by default | Start with one ReAct loop; add graph only for durable multi-step *workflows* with human interrupts |
| Phase 3 “more roles” | Scale with better retrieval and routing first |

### Two products, one platform (recommended product split)

1. **Companion** (new): interactive learning + pair programming. Single agent. Scale-to-zero. Optimized for $/session and pedagogy.
2. **Fleet** (existing): overnight / batch project completion with PM→Dev→Reviewer and human merge. Keep as a *mode* or separate SKU, not the default path for learners.

Do not force learners through a 3-agent DAG to ask “why does this test fail?”

---

## Recommended build order (SDLC)

### Phase A — Companion MVP (cost-first)

1. One FastAPI (or similar) service: session + ReAct + tools + verifier.
2. Modes as system prompts + tool allowlists (`tutor`, `pair`, `implement`).
3. Haiku router; Sonnet only for `implement` when edit tools are used.
4. Per-user LiteLLM key; daily USD cap; iteration/tool caps in code.
5. Learner state table (mastery map, last misconception, streak).
6. Receipts: tokens, model, stop reason, verifier pass/fail — same spirit as MartinLoop.

**Exit gate:** a 20-minute lesson + one small coding task stays under a published $/session budget; forced stuck-loop hits the cap and escalates cleanly.

### Phase B — Context efficiency

1. Repo map / symbol index + retrieval before reads.
2. Tool-schema filtering by mode.
3. Session compaction after N turns.
4. Graduated hint policy (conceptual → pointer → partial → full).

### Phase C — Optional multi-agent (only with evidence)

Add a second agent **only** when an eval shows a clear win, for example:

- Independent parallel review of a large PR (voting), or
- Overnight fleet-style project mode reusing today's PM/Dev/Reviewer.

Require: independence of subtasks, concurrency ≤2, shared verifier, same budget hooks.

---

## Mapping Anthropic patterns → companion features

| Pattern ([Anthropic](https://www.anthropic.com/engineering/building-effective-agents)) | Companion use |
|----------------------------------------------------------------------------------------|---------------|
| Augmented LLM | Default: tools + memory + retrieval |
| Routing | Mode + difficulty → model + prompt |
| Prompt chaining | Lesson plan → exercise → feedback (fixed pedagogy pipeline) |
| Evaluator–optimizer | Code draft → rubric/tests → refine (capped) |
| Orchestrator–workers | Deferred; only for breadth-first audits |
| Autonomous multi-agent | Fleet SKU only |

---

## Decision checklist (use before adding any new agent)

Answer yes to **all** before spawning another LLM worker:

1. Are the subtasks truly independent (no shared mutable files)?
2. Will a deterministic router / skill do the same job cheaper?
3. Is there a verifier that does not need a second LLM?
4. Have we measured single-agent failure on this task class?
5. Is the expected quality gain worth ~2–15× tokens?

If any answer is no → stay single-agent.

---

## Sources (primary)

- Anthropic — [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- Cutler — [Three topologies: single, supervisor, swarm](https://cutler.sg/blog/2026-05-three-topologies-single-agent-supervisor-swarm) (incl. ~15× token tax)
- Future AGI — [How to build agent loops](https://futureagi.com/blog/loop-engineering/how-to-do-loop-engineering/)
- MartinLoop — [Bounded contracts / budgets / receipts](https://github.com/Keesan12/martin-loop/)
- GitHub — [Copilot context + model routing](https://github.blog/ai-and-ml/github-copilot/getting-more-from-each-token-how-copilot-improves-context-handling-and-model-routing/)
- arXiv — [Cost attribution of context-compression gateways](https://arxiv.org/abs/2609.22114)
- Augment — [Single vs multi-agent token economics](https://www.augmentcode.com/guides/single-agent-vs-multi-agent-ai)

---

## Next concrete engineering step

When we start the companion product repo (or a `companion/` tree here):

1. Scaffold **one** agent service with tutor/pair/implement modes.
2. Reuse LiteLLM budgets; do **not** deploy PM/reviewer Deployments for it.
3. Add an eval harness that reports $/successful lesson and $/green coding task.
4. Only then decide whether overnight “fleet mode” remains a separate Argo CD app or a queued job behind the same gateway.
