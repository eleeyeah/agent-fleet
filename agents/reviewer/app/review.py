"""LLM review of a PR diff against the task's acceptance criteria.

The reviewer is deliberately constrained: it reads and judges, it cannot write code
or merge. Its approval is advisory — branch protection still demands a human."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from fleet_common.config import Settings
from fleet_common.llm import chat_model
from fleet_common.models import Task

log = logging.getLogger("review")

MAX_DIFF_CHARS = 60_000

SYSTEM_PROMPT = """You are a rigorous code reviewer. You receive one pull request diff
and the task it implements. Judge ONLY what is in the diff.

Check, in order:
1. Does the diff satisfy EVERY acceptance criterion? Point to evidence in the diff.
2. Are there tests covering the new behavior, and do they actually assert it?
3. Correctness problems: bugs, unhandled edge cases the criteria imply, security issues.
4. Scope: flag unrelated changes, deleted/weakened tests, or touches to .gitea/workflows/
   (an agent must never modify CI — treat that as an automatic REQUEST_CHANGES).

Verdict rules:
- APPROVED only if every criterion is met and tests are real.
- REQUEST_CHANGES otherwise, with specific, actionable feedback the developer can apply.
Be strict but fair; do not request stylistic rewrites."""


class ReviewVerdict(BaseModel):
    verdict: str = Field(description="APPROVED or REQUEST_CHANGES")
    summary: str = Field(description="2-4 sentence overall assessment")
    points: list[str] = Field(default_factory=list, description="specific findings / required changes")


def review_pr(settings: Settings, task: Task, diff: str) -> ReviewVerdict:
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n...[diff truncated]"
    llm = chat_model(settings).with_structured_output(ReviewVerdict)
    verdict: ReviewVerdict = llm.invoke([
        ("system", SYSTEM_PROMPT),
        ("user",
         f"# Task: {task.title}\n\n{task.spec}\n\n"
         "## Acceptance criteria\n- " + "\n- ".join(task.acceptance_criteria) + "\n\n"
         f"## Diff\n```diff\n{diff}\n```"),
    ])
    if verdict.verdict not in ("APPROVED", "REQUEST_CHANGES"):
        verdict.verdict = "REQUEST_CHANGES"  # fail closed
    return verdict


def format_review(verdict: ReviewVerdict, task: Task) -> str:
    points = ("\n".join(f"- {p}" for p in verdict.points)) if verdict.points else "- (none)"
    return (
        f"{verdict.summary}\n\n**Findings:**\n{points}\n\n---\n"
        f"Task `{task.task_id}` · correlation_id `{task.correlation_id}`\n"
        "_Automated review. A human approval is still required to merge._"
    )
