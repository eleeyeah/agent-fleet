"""The coding loop: a bounded ReAct agent with file + command tools, scoped to one
task's working directory. The definition of done is executable — pytest must pass
in-pod before a PR is opened; the model's own claim of success is never trusted.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from fleet_common.config import Settings
from fleet_common.llm import chat_model
from fleet_common.models import Task

log = logging.getLogger("coder")

MAX_TOOL_OUTPUT = 8_000

SYSTEM_PROMPT = """You are a senior backend developer implementing ONE task in an
existing repository. Work only inside the repository you are given.

Process:
1. Inspect the existing code (list_files, read_file) before writing anything.
2. Implement the task spec. Write focused, clean code — no unrelated changes.
3. Write pytest tests covering the acceptance criteria.
4. Run `pytest -q` with run_command and iterate until ALL tests pass.
5. When tests pass, reply with a short summary of what you changed (no tool calls).

Rules:
- Never modify or delete tests just to make them pass.
- Never touch .gitea/workflows/.
- Dependencies go in pyproject.toml or requirements.txt, then `pip install -e .`
  or `pip install -r requirements.txt` before running tests.
"""


def _run(cmd: str, cwd: Path, timeout: int) -> str:
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd], cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: command timed out after {timeout}s"
    except Exception as exc:
        # A tool failure is feedback for the model, never a crash of the agent loop
        return f"ERROR: command failed to execute: {exc}"
    out = (proc.stdout or "") + (("\n--- stderr ---\n" + proc.stderr) if proc.stderr else "")
    out = out.strip() or "(no output)"
    if len(out) > MAX_TOOL_OUTPUT:
        out = out[:MAX_TOOL_OUTPUT // 2] + "\n...[truncated]...\n" + out[-MAX_TOOL_OUTPUT // 2:]
    return f"exit_code={proc.returncode}\n{out}"


def run_task(settings: Settings, task: Task, workdir: Path) -> tuple[bool, str]:
    """Run the coding agent for one task. Returns (tests_green, summary_or_error)."""
    workdir = workdir.resolve()

    def safe(path: str) -> Path:
        p = (workdir / path).resolve()
        if not p.is_relative_to(workdir):
            raise ValueError(f"path escapes the workspace: {path}")
        return p

    @tool
    def list_files() -> str:
        """List all files in the repository (tracked and untracked, excluding .git)."""
        files = sorted(
            str(p.relative_to(workdir))
            for p in workdir.rglob("*")
            if p.is_file() and ".git" not in p.parts
        )
        return "\n".join(files[:500]) or "(empty repository)"

    @tool
    def read_file(path: str) -> str:
        """Read a file from the repository. `path` is relative to the repo root."""
        p = safe(path)
        if not p.is_file():
            return f"ERROR: no such file: {path}"
        content = p.read_text(errors="replace")
        return content if len(content) <= MAX_TOOL_OUTPUT else content[:MAX_TOOL_OUTPUT] + "\n...[truncated]"

    @tool
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file. `path` is relative to the repo root."""
        p = safe(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {path} ({len(content)} bytes)"

    @tool
    def run_command(command: str) -> str:
        """Run a shell command in the repo root (e.g. `pytest -q`, `pip install -e .`).
        Output is truncated; long-running commands time out."""
        return _run(command, workdir, settings.command_timeout_s)

    agent = create_react_agent(
        chat_model(settings),
        tools=[list_files, read_file, write_file, run_command],
        prompt=SYSTEM_PROMPT,
    )

    user = (
        f"# Task: {task.title}\n\n{task.spec}\n\n"
        "## Acceptance criteria\n- " + "\n- ".join(task.acceptance_criteria)
    )
    try:
        result = agent.invoke(
            {"messages": [("user", user)]},
            config={"recursion_limit": settings.max_iterations},  # hard iteration bound
        )
        summary = result["messages"][-1].content
    except Exception as exc:  # includes GraphRecursionError = iteration budget spent
        return False, f"agent loop failed: {exc}"

    # Executable verification — the merge gate starts here, not in CI.
    verdict = _run("pytest -q", workdir, settings.command_timeout_s)
    if verdict.startswith("exit_code=0"):
        return True, str(summary)
    return False, f"tests failing after agent finished:\n{verdict}"
