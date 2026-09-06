"""backend-dev agent: consumes ready tasks from the work queue, implements each on an
isolated branch (one branch per task attempt — worktree isolation, risk #3), verifies
with pytest in-pod, then opens a PR. It never merges (risk #7)."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path

from nats.aio.msg import Msg
from nats.js.api import ConsumerConfig

from coder import run_task
from fleet_common import bus, tracing
from fleet_common.config import settings
from fleet_common.gitea import GiteaClient
from fleet_common.models import AgentEvent, EventType, Task, TaskStatus

log = logging.getLogger("dev")

# A coding attempt can legitimately take a long time; keep the JetStream redelivery
# window generous and send working-heartbeats while the attempt runs.
ACK_WAIT_S = 2 * 3600


def git(workdir: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=workdir, check=True, capture_output=True, text=True)


async def heartbeat(msg: Msg, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await msg.in_progress()
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except TimeoutError:
            pass


async def handle_task(js, gitea: GiteaClient, msg: Msg) -> None:
    task = Task.model_validate_json(msg.data)
    tracing.correlation_id.set(task.correlation_id)

    stop = asyncio.Event()
    hb = asyncio.create_task(heartbeat(msg, stop))
    workdir = Path(settings.work_dir) / f"{task.project_id}-{task.task_id}-a{task.attempts + 1}"
    try:
        task.attempts += 1
        task.status = TaskStatus.IN_PROGRESS
        task.branch = f"task/{task.task_id}-a{task.attempts}"
        await bus.save_task(js, task)
        await bus.publish_event(js, AgentEvent(
            event_type=EventType.TASK_STARTED, project_id=task.project_id,
            task_id=task.task_id, agent=settings.agent_name,
            correlation_id=task.correlation_id, payload={"attempt": task.attempts},
        ))
        log.info("task %s attempt %d -> %s", task.task_id, task.attempts, task.branch)

        # Isolated workspace: fresh clone per attempt
        if workdir.exists():
            shutil.rmtree(workdir)
        workdir.mkdir(parents=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", gitea.authed_clone_url(task.repo), str(workdir)],
            check=True, capture_output=True, text=True,
        )
        git(workdir, "checkout", "-b", task.branch)

        ok, summary = await asyncio.to_thread(run_task, settings, task, workdir)

        if not ok:
            raise RuntimeError(summary)

        git(workdir, "add", "-A")
        git(workdir, "commit", "-m", f"{task.title}\n\ntask: {task.task_id}\ncorrelation_id: {task.correlation_id}")
        git(workdir, "push", "origin", task.branch)

        body = (
            f"{summary}\n\n---\n"
            f"**Task:** `{task.task_id}` (attempt {task.attempts})\n"
            "**Acceptance criteria:**\n- " + "\n- ".join(task.acceptance_criteria) + "\n\n"
            f"correlation_id: `{task.correlation_id}`\n\n"
            "_Opened by backend-dev-agent. Tests pass in-pod; CI must confirm; "
            "reviewer + human approval required to merge._"
        )
        pr = await asyncio.to_thread(
            gitea.create_pr, task.repo, task.branch, f"[{task.task_id}] {task.title}", body
        )
        task.status = TaskStatus.IN_REVIEW
        task.pr_number = pr
        await bus.save_task(js, task)
        await bus.publish_event(js, AgentEvent(
            event_type=EventType.PR_OPENED, project_id=task.project_id,
            task_id=task.task_id, agent=settings.agent_name,
            correlation_id=task.correlation_id,
            payload={"pr_number": pr, "branch": task.branch},
        ))
        log.info("task %s -> PR #%d", task.task_id, pr)

    except Exception as exc:
        log.exception("task %s attempt failed", task.task_id)
        task.status = TaskStatus.FAILED
        task.last_error = str(exc)[:4000]
        await bus.save_task(js, task)
        await bus.publish_event(js, AgentEvent(
            event_type=EventType.TASK_FAILED, project_id=task.project_id,
            task_id=task.task_id, agent=settings.agent_name,
            correlation_id=task.correlation_id, payload={"error": task.last_error[:500]},
        ))
    finally:
        stop.set()
        await hb
        shutil.rmtree(workdir, ignore_errors=True)
        await msg.ack()


async def main() -> None:
    tracing.setup("backend-dev-agent", settings.otel_endpoint)
    nc, js = await bus.connect(settings.nats_url)
    gitea = GiteaClient(settings)

    sub = await js.pull_subscribe(
        bus.SUBJECT_READY,
        durable="dev-tasks",
        stream=bus.STREAM_TASKS,
        config=ConsumerConfig(ack_wait=ACK_WAIT_S, max_deliver=2),
    )
    log.info("backend-dev up (model=%s, max_iterations=%d)", settings.model, settings.max_iterations)
    try:
        while True:
            try:
                msgs = await sub.fetch(1, timeout=30)
            except TimeoutError:
                continue
            except Exception:
                log.exception("fetch failed; retrying in 5s")
                await asyncio.sleep(5)
                continue
            for msg in msgs:
                await handle_task(js, gitea, msg)  # one task at a time, by design
    finally:
        await nc.drain()


if __name__ == "__main__":
    asyncio.run(main())
