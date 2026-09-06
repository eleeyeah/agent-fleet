"""Task schema shared by all agents. The correlation_id set at brief submission is
propagated through every task, event, log line, PR body, and escalation (risk #6)."""

from __future__ import annotations

import time
import uuid
from enum import StrEnum

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    PENDING = "pending"          # created by PM, dependencies not yet satisfied
    READY = "ready"              # published to the work queue
    IN_PROGRESS = "in_progress"  # a dev agent picked it up
    IN_REVIEW = "in_review"      # PR opened, reviewer + human gate pending
    DONE = "done"                # PR merged by a human
    FAILED = "failed"            # attempt failed; PM decides retry vs escalate
    ESCALATED = "escalated"      # bounded retries exhausted -> Gitea issue for a human


class EventType(StrEnum):
    TASK_STARTED = "task_started"
    TASK_FAILED = "task_failed"
    PR_OPENED = "pr_opened"        # dev agent finished; PR exists
    PR_REVIEWED = "pr_reviewed"    # reviewer posted a verdict
    PR_MERGED = "pr_merged"        # human merged (via Gitea webhook)
    ESCALATION = "escalation"
    PROJECT_DONE = "project_done"


class ProjectBrief(BaseModel):
    project_id: str
    title: str
    description: str
    constraints: list[str] = Field(default_factory=list)
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class Task(BaseModel):
    task_id: str
    project_id: str
    title: str
    spec: str                                  # what to build, written by the PM
    acceptance_criteria: list[str]             # what the reviewer checks against
    depends_on: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    correlation_id: str = ""
    repo: str = ""                             # gitea org/repo
    branch: str = ""                           # task/<task_id>
    pr_number: int | None = None
    last_error: str = ""

    @property
    def kv_key(self) -> str:
        return f"task.{self.project_id}.{self.task_id}"


class AgentEvent(BaseModel):
    event_type: EventType
    project_id: str
    task_id: str = ""
    agent: str = ""
    correlation_id: str = ""
    payload: dict = Field(default_factory=dict)
    ts: float = Field(default_factory=time.time)
