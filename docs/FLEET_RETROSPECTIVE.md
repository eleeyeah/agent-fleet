# Fleet retrospective — what the small FastAPI loop proved

**Context:** Phase 1 agent fleet (PM → backend-dev → reviewer) coordinated via git + NATS,
with LiteLLM budgets and human merge on `main`. The designed proving run is a greenfield
`todo-api` (small FastAPI CRUD + pytest). See [PHASES.md](PHASES.md), [ARCHITECTURE.md](ARCHITECTURE.md).

**Primary next intent:** [intent/internship-success-loop.md](../intent/internship-success-loop.md) —
a personal Anthropic-native short-cycle harness for internship success, not fleet scale-out.

---

## Snapshot of the previous approach

```text
one-line ProjectBrief
  → pm-agent decomposes to a validated task DAG (≤8 tasks)
  → backend-dev ReAct loop (files + shell + pytest) per task branch
  → open PR; reviewer LLM vs acceptance criteria; CI pytest
  → human merges; PM unlocks dependent tasks / PROJECT_DONE
```

Strengths already encoded: git as coordination, constrained roles, executable done-condition,
attempt/budget caps, correlation IDs, escalation instead of infinite retry
([RISKS.md](RISKS.md)).

Intake weakness: [`scripts/submit-project.sh`](../scripts/submit-project.sh) sends a JSON brief
with a free-text `description` — there is no versioned `intent.md` gate. Contrast with
[intent/examples/todo-api.intent.md](../intent/examples/todo-api.intent.md).

---

## What a successful todo-api-shaped run validates

If Phase 1 gates pass on that shape of work, the fleet has shown:

| Area | Evidence |
|------|----------|
| Wiring | Brief → DAG → branch → PR → review event → merge webhook → next task |
| Rails | Branch protection + CI + human merge; agents cannot ship alone |
| Bounds | Iteration / attempt limits and LiteLLM virtual-key budgets can stop spend |
| Greenfield decompose | PM + schema validation can split a clear CRUD API into 3–5 tasks |
| Local verify | In-pod pytest as ground truth beats “I fixed it” |
| Operability | correlation_id + spend dashboard make one small project debuggable |

Those are real engineering wins for a **lab / overnight project** SKU.

---

## What the small FastAPI run does *not* prove

The internship environment is an **established, unfamiliar codebase** with mentor review,
estimation, and early escalation of ambiguity. todo-api does not stress that.

| Dimension | todo-api / fleet lab | Internship-realistic work |
|-----------|----------------------|---------------------------|
| Codebase | Empty or template | Large product tree, conventions, tribal knowledge |
| Intake | One sentence | Ticket with gaps; must write open questions before coding |
| Decomposition | Obvious CRUD slices | Partial ownership, hidden deps, “too large” calls |
| Verification | Local pytest | Lint, integration, pipelines, flaky env setup |
| Review | Third LLM + you merge | Mentor quality bar; fewer rounds; act on feedback |
| Cost | Short Sonnet loops on tiny context | Context bloat, retries, 3× role LLMs compound |
| Failure | Impossible AC → escalation issue | Stuck identical approaches; partial merges; thrash |
| Skills transfer | Greenfield FastAPI | Scripts→app code, API clients, test automation, logging/ETL touches |

**Conclusion:** the loop “kind of working” on a small FastAPI is necessary confidence for
fleet rails; it is **not** evidence the same topology is the right daily tool for internship
tickets, nor that it is cost-efficient in cloud for interactive professional work.

---

## Keep vs change

### Keep (carry into the personal loop)

- Executable verifiers (tests/build) as done
- Hard budgets and iteration caps **outside** prompts
- Human as merge / mentor gate
- Correlation / receipts for spend and stop reason
- Small blast radius (one task / one PR)
- Escalation when retries are exhausted

### Change (for internship-success track)

| From | To |
|------|----|
| Always-on PM + Dev + Reviewer pods | Single session / single agent + skills |
| One-line NATS brief | Versioned `intent.md` (and `plan.md`) per ticket |
| LLM reviewer on every PR | Deterministic CI + adversarial self-review; human mentor for real approval |
| Greenfield-only proving story | Practice on unfamiliar code exploration + bug/feature playbooks |
| Phase 2/3 = more roles / EKS fleet | Personal short-cycle harness first ([AI_NATIVE_SDLC.md](AI_NATIVE_SDLC.md)) |

### Defer

- KEDA scale-out, more permanent roles, A2A multi-agent — until personal loop metrics exist
- Deploying this stack into employer infrastructure

---

## Recommendation

Treat the fleet as a **successful lab prototype of gates and coordination**, not as the
product you take into the internship day-to-day. Build the next increment around
[intent/internship-success-loop.md](../intent/internship-success-loop.md): artifact-gated
Explore → Plan → Implement → Verify → self-review → PR, cost-bounded, single-agent default.
