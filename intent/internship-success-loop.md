# Intent: Internship-success agentic loop

**Status:** draft — primary product intent for this repo’s next track  
**Author:** Ilie Honciuc  
**Created:** 2026-09-23  
**Horizon:** Software Development Internship starting 2026-10-01 (~6 months)

This file is the durable intake artifact (Anthropic AI-native SDLC shape).  
It is **not** an employment contract, bonus target, or employer document.  
Employer-signed development plans stay private and off this repository.

---

## Problem

I am transitioning from strong DevOps / infrastructure work into application
development on an established, unfamiliar product codebase. Success depends on
repeatable professional habits:

- Understanding code and conventions before changing them
- Shipping small, reviewable pull requests with tests
- Tracing bugs from ticket → repro → line → fix
- Estimating scope and **flagging ambiguity early**
- Acting on review feedback without repeating the same mistakes
- Documenting work so others can continue it

I already proved a multi-agent **fleet** loop on a small greenfield FastAPI
exercise. That environment is not the internship environment. I need a
**personal, short-cycle, Anthropic-native agentic loop** as a daily harness —
not a tutoring product and not an always-on cloud agent fleet at the employer.

## Proposed outcome

A personal AI-native workflow I can run per ticket:

1. Write / refine **`intent.md`** for the ticket (problem, outcome, constraints, open questions)
2. **Explore** the relevant code (read-only) and capture notes / repo anchors
3. Produce **`plan.md`** (files, order, risks, test approach) before non-trivial edits
4. **Implement** a small blast-radius change with automated tests
5. **Verify** with the real check (tests / linter / build) — never self-assessment alone
6. **Self-review** against the plan (adversarial pass) before asking a human mentor
7. Open a **PR** with evidence (what changed, how verified, residual risks)

Default topology: **one coding agent + deterministic gates**.  
Human mentor / reviewer remains the real approval gate.

## Affected users and systems

| Who / what | How |
|------------|-----|
| Intern (me) | Daily driver for tickets, bugs, small features |
| Mentor / reviewers | Receive cleaner PRs; fewer “same comment twice” rounds |
| This `agent-fleet` repo | Design home, templates, later thin harness; fleet stays a rehearsal lab |
| Employer product repos | Consumed read/write only under policy; no secrets or confidential plans in git |

## Constraints

- Cost-aware: budgets and iteration caps outside prompts; prefer Haiku for route/summarize, frontier models for plan/build
- Single-agent default; no always-on PM + Dev + Reviewer pods as the internship tool
- No confidential employer materials, customer data, or signed plans in this repository
- Human merge / mentor review is never bypassed by an agent “approval”
- Short cycles: one vertical slice per session when possible; escalate when stuck on the same failure
- Build on DevOps strengths: scripts → tested app code, API clients, pipeline/test automation, logging — without pretending those replace product onboarding

## Internship phase mapping (indicative orientation only)

Sanitized phase shape for loop design. Benchmarks are **personal practice targets**, not contractual claims.

| Phase | Focus | Loop emphasis | Personal practice signals |
|-------|--------|---------------|---------------------------|
| Months 1–2 | Understand and fix | Explore, debug playbook, tiny PRs, convention notes | Many small merged PRs; several bugs traced end-to-end; observe reviews; improve onboarding notes where allowed |
| Months 3–4 | Build under guidance | Plan → implement → tests; estimation in intent; act on review | Few clearly scoped features; tests without being asked; aim for fewer review rounds; start helpful review comments |
| Months 5–6 | Own a small feature | Full ticket ownership; risk/side-effect section in plan; docs | One feature with tests + docs; proactive “too large / unclear” flags; supervised support exposure if offered |

## Task-type playbooks (skills, not extra agent pods)

| Task type | Starting bias |
|-----------|----------------|
| Bugfix | Repro → failing test → root cause → minimal fix → verify |
| Small feature | Intent → explore → plan → implement + tests → self-review → PR |
| Script → app code | Extract behavior, add tests, keep ops contracts clear |
| Internal tool / REST API client | Spec auth + error handling + tests before UI polish |
| Test / pipeline work | Make the verifier better; keep changes reviewable |
| Logging / ETL touchpoints | Prefer structured logs; tiny diffs; call out side effects early |

## Success signals (for this intent)

- I can open this file and a per-ticket intent and know the next play without inventing process
- Time from ticket clarity → first PR draft drops as months progress
- Share of PRs with tests and a short verification note rises
- Open questions are written **before** large implementation spend
- Token/$ spend per ticket stays bounded and visible
- Fleet retrospective lessons applied: do not treat todo-api success as readiness for a large unfamiliar codebase

## Non-goals

- Building a classroom / tutoring product
- Deploying the three-agent fleet into employer cloud as the daily path
- Claiming the greenfield FastAPI proving run equals internship readiness
- Committing confidential employer documents or production secrets
- Multi-agent orchestration for ordinary sequential coding tasks

## Open questions

1. First runtime shape: Claude Code + templates only, vs thin local harness wrapping Messages API / LiteLLM?
2. Where do per-ticket `intent.md` / `plan.md` live day-to-day (personal notes repo vs branch in the work repo)?
3. Which verifier commands will dominate early (unit tests, lint, integration) once the real stack is known?
4. How much of the existing fleet (Gitea, NATS, reviewer pod) is kept as a lab vs retired for the personal loop?

## Next artifact

When this intent is accepted: draft `spec.md` for the personal loop MVP (templates, checklist, optional thin runner) — still docs-first before platform work.
