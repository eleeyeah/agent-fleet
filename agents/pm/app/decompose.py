"""Brief -> task DAG via a small LangGraph graph: decompose -> validate (-> retry once).

The PM produces tasks, never code. Validation is executable, not vibes: unique ids,
existing deps, acyclic graph, bounded size, acceptance criteria present.
"""

from __future__ import annotations

import logging
import re
from graphlib import CycleError, TopologicalSorter
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from fleet_common.config import Settings
from fleet_common.llm import chat_model
from fleet_common.models import ProjectBrief, Task

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the project manager of a small software team. Decompose the
project brief into between 2 and {max_tasks} implementation tasks for a backend developer.

Rules:
- Each task must be independently implementable and verifiable by its acceptance criteria.
- Acceptance criteria must be concrete and testable (the reviewer checks the PR against them,
  CI runs pytest). Every task's spec must require tests for the code it adds.
- task_id: short kebab-case slug, e.g. "scaffold-api".
- depends_on may only reference task_ids from this same list. Prefer few dependencies.
- The FIRST task must scaffold the project skeleton (pyproject/requirements, package layout,
  a trivial passing test) so CI is green from the start.
"""


class TaskDraft(BaseModel):
    task_id: str
    title: str
    spec: str
    acceptance_criteria: list[str]
    depends_on: list[str] = Field(default_factory=list)


class TaskPlan(BaseModel):
    """The full decomposition of the brief."""
    tasks: list[TaskDraft]


class DecomposeState(TypedDict):
    brief: ProjectBrief
    plan: TaskPlan | None
    feedback: str
    attempts: int


def _validate(plan: TaskPlan, max_tasks: int) -> list[str]:
    problems: list[str] = []
    if not 2 <= len(plan.tasks) <= max_tasks:
        problems.append(f"need between 2 and {max_tasks} tasks, got {len(plan.tasks)}")
    ids = [t.task_id for t in plan.tasks]
    if len(set(ids)) != len(ids):
        problems.append("duplicate task_ids")
    for t in plan.tasks:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,40}", t.task_id):
            problems.append(f"task_id '{t.task_id}' is not a kebab-case slug")
        if not t.acceptance_criteria:
            problems.append(f"task '{t.task_id}' has no acceptance criteria")
        for dep in t.depends_on:
            if dep not in ids:
                problems.append(f"task '{t.task_id}' depends on unknown '{dep}'")
    try:
        # static_order() is lazy — materialize it or cycles go undetected
        list(TopologicalSorter({t.task_id: set(t.depends_on) for t in plan.tasks}).static_order())
    except CycleError:
        problems.append("dependency cycle detected")
    return problems


def build_graph(settings: Settings, checkpointer=None):
    llm = chat_model(settings).with_structured_output(TaskPlan)

    def decompose(state: DecomposeState) -> dict:
        brief = state["brief"]
        user = (
            f"Project: {brief.title}\n\nBrief:\n{brief.description}\n\n"
            + (f"Constraints:\n- " + "\n- ".join(brief.constraints) + "\n\n" if brief.constraints else "")
            + (f"Your previous plan was rejected: {state['feedback']}\nFix those problems." if state["feedback"] else "")
        )
        plan = llm.invoke([
            ("system", SYSTEM_PROMPT.format(max_tasks=settings.max_project_tasks)),
            ("user", user),
        ])
        return {"plan": plan, "attempts": state["attempts"] + 1}

    def validate(state: DecomposeState) -> dict:
        problems = _validate(state["plan"], settings.max_project_tasks)
        return {"feedback": "; ".join(problems)}

    def route(state: DecomposeState) -> str:
        if not state["feedback"]:
            return "ok"
        if state["attempts"] >= 3:
            raise ValueError(f"decomposition failed after {state['attempts']} attempts: {state['feedback']}")
        log.warning("plan rejected (attempt %d): %s", state["attempts"], state["feedback"])
        return "retry"

    g = StateGraph(DecomposeState)
    g.add_node("decompose", decompose)
    g.add_node("validate", validate)
    g.add_edge(START, "decompose")
    g.add_edge("decompose", "validate")
    g.add_conditional_edges("validate", route, {"ok": END, "retry": "decompose"})
    return g.compile(checkpointer=checkpointer)


def decompose_brief(settings: Settings, brief: ProjectBrief, checkpointer=None) -> list[Task]:
    graph = build_graph(settings, checkpointer)
    final = graph.invoke(
        {"brief": brief, "plan": None, "feedback": "", "attempts": 0},
        config={"configurable": {"thread_id": f"decompose-{brief.project_id}"}},
    )
    plan: TaskPlan = final["plan"]
    return [
        Task(
            task_id=d.task_id,
            project_id=brief.project_id,
            title=d.title,
            spec=d.spec,
            acceptance_criteria=d.acceptance_criteria,
            depends_on=d.depends_on,
            correlation_id=brief.correlation_id,
            repo=brief.project_id,
        )
        for d in plan.tasks
    ]
