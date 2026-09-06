"""Offline unit tests for the fleet's pure logic (no cluster, no LLM, no network).

Run via scripts/validate.sh, or directly:
  PYTHONPATH=agents/common:agents/pm/app:agents/backend-dev/app:agents/reviewer/app \
    pytest agents/tests -q
"""

from pathlib import Path

import pytest

from fleet_common.config import Settings
from fleet_common.gitea import GiteaClient
from fleet_common.models import AgentEvent, EventType, ProjectBrief, Task, TaskStatus

from decompose import TaskDraft, TaskPlan, _validate          # pm agent
from coder import _run                                         # backend-dev agent
from review import ReviewVerdict, format_review                # reviewer agent

# Both pm and reviewer ship a main.py (each container mounts only its own /app);
# in tests, load the reviewer's by path to avoid the module-name collision.
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "reviewer_main", Path(__file__).parent.parent / "reviewer" / "app" / "main.py"
)
_reviewer_main = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_reviewer_main)
parse_task_branch = _reviewer_main.parse_task_branch


# ------------------------------------------------------------------- models

def test_task_roundtrip_and_kv_key():
    t = Task(
        task_id="scaffold-api", project_id="todo-api", title="Scaffold",
        spec="do it", acceptance_criteria=["ci green"], correlation_id="cid-1",
    )
    assert t.kv_key == "task.todo-api.scaffold-api"
    assert t.status == TaskStatus.PENDING and t.attempts == 0
    clone = Task.model_validate_json(t.model_dump_json())
    assert clone == t


def test_brief_gets_correlation_id():
    b = ProjectBrief(project_id="p", title="t", description="d")
    assert len(b.correlation_id) == 36  # uuid4


def test_event_subject_types():
    ev = AgentEvent(event_type=EventType.PR_MERGED, project_id="p", task_id="t")
    assert f"events.{ev.event_type}" == "events.pr_merged"


# --------------------------------------------------------- PM: DAG validation

def _draft(tid, deps=(), criteria=("works",)):
    return TaskDraft(task_id=tid, title=tid, spec="s",
                     acceptance_criteria=list(criteria), depends_on=list(deps))


def test_valid_plan_passes():
    plan = TaskPlan(tasks=[_draft("scaffold"), _draft("api", deps=["scaffold"])])
    assert _validate(plan, max_tasks=8) == []


def test_cycle_detected():
    plan = TaskPlan(tasks=[_draft("a", deps=["b"]), _draft("b", deps=["a"])])
    assert any("cycle" in p for p in _validate(plan, 8))


def test_unknown_dependency():
    plan = TaskPlan(tasks=[_draft("a", deps=["ghost"]), _draft("b")])
    assert any("unknown" in p for p in _validate(plan, 8))


def test_bounds_and_criteria():
    assert any("between 2 and" in p for p in _validate(TaskPlan(tasks=[_draft("solo")]), 8))
    plan = TaskPlan(tasks=[_draft("a"), _draft("b", criteria=())])
    assert any("no acceptance criteria" in p for p in _validate(plan, 8))
    plan = TaskPlan(tasks=[_draft("a"), _draft("Bad_Slug!")])
    assert any("kebab-case" in p for p in _validate(plan, 8))


# ------------------------------------------------------- dev: command runner

def test_run_command_captures_exit_and_output(tmp_path: Path):
    out = _run("echo hello && exit 3", tmp_path, timeout=10)
    assert out.startswith("exit_code=3") and "hello" in out


def test_run_command_timeout_is_error_not_crash(tmp_path: Path):
    # In pods this is the timeout message; in restricted sandboxes the kill itself can
    # be denied — either way the tool must return an ERROR string, never raise.
    assert _run("sleep 5", tmp_path, timeout=1).startswith("ERROR")


# ------------------------------------------------- reviewer: branch parsing

@pytest.mark.parametrize("branch,expected", [
    ("task/scaffold-api-a1", "scaffold-api"),
    ("task/a-b-c-a12", "a-b-c"),
    ("task/noattempt", None),
    ("main", None),
    ("feature/task-like", None),
])
def test_parse_task_branch(branch, expected):
    assert parse_task_branch(branch) == expected


def test_format_review_mentions_human_gate():
    t = Task(task_id="x", project_id="p", title="X", spec="s",
             acceptance_criteria=["c"], correlation_id="cid")
    text = format_review(ReviewVerdict(verdict="APPROVED", summary="ok", points=[]), t)
    assert "human approval" in text and "cid" in text


# ---------------------------------------------------------- gitea client

def test_authed_clone_url_embeds_bot_credentials():
    s = Settings(gitea_url="http://gitea-http.fleet-git.svc:3000",
                 gitea_user="dev-bot", gitea_token="tok123")
    url = GiteaClient(s).authed_clone_url("todo-api")
    assert url == "http://dev-bot:tok123@gitea-http.fleet-git.svc:3000/agents/todo-api.git"
