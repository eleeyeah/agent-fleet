# Intent example: todo-api (rewrite of the fleet brief)

**Status:** example only — shows the gap between today’s one-line brief and a real intent  
**Original fleet intake:** `submit-project.sh todo-api "Small FastAPI todo API with CRUD endpoints and pytest tests"`

---

## Problem

We need a tiny greenfield HTTP API to prove the agent-fleet Phase 1 loop end-to-end
(brief → task DAG → implement → pytest CI → review → human merge → PROJECT_DONE).

## Proposed outcome

A small FastAPI service with CRUD for todo items, packaged so `pytest` is green in CI,
with enough structure that the PM can split work into a few mergeable PRs.

## Affected users and systems

- Fleet operators validating Phase 1 gates
- `pm-agent`, `backend-dev`, `reviewer`, Gitea, LiteLLM (lab stack only)

## Constraints

- Greenfield repo from template; no legacy codebase
- Python / FastAPI / pytest only
- ≤ ~8 PM tasks; each PR must carry tests
- Agents never merge `main`

## Open questions

- Persistence: in-memory vs SQLite for the proving run?
- Auth: none for Phase 1, or a trivial API key?
- Exact acceptance criteria per CRUD verb?

## Why this is a weak internship rehearsal

| This intent / todo-api | Internship-realistic ticket |
|------------------------|-----------------------------|
| Empty or template repo | Large unfamiliar product codebase |
| One-line description was enough for PM | Ambiguity, missing info, estimation, early escalation |
| CRUD shape is obvious | Cross-cutting behavior, conventions, side effects |
| Pytest in-pod is the whole verifier | Pipelines, integration, review culture |
| Three agents always on | Personal short cycle + human mentor |

Use [`../internship-success-loop.md`](../internship-success-loop.md) as the primary intent.
Use this file only to contrast fleet lab intake vs professional ticket intake.
