"""pm-agent: the supervisor. Decomposes briefs into task DAGs, dispatches ready tasks,
tracks progress via events, retries within bounds, and escalates to humans (Gitea
issues) when stuck. It coordinates — it never writes code (constraint from the
Drafter/Reviewer/Integrator pattern).
"""

from __future__ import annotations

import asyncio
import logging

from nats.aio.msg import Msg

from decompose import decompose_brief
from fleet_common import bus, tracing
from fleet_common.config import settings
from fleet_common.gitea import GiteaClient
from fleet_common.models import AgentEvent, EventType, ProjectBrief, Task, TaskStatus

log = logging.getLogger("pm")


def make_checkpointer():
    """Durable LangGraph state in the Patroni `agentstate` db; None = in-memory."""
    if not settings.checkpoint_db_uri:
        return None
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection
        from psycopg.rows import dict_row

        conn = Connection.connect(settings.checkpoint_db_uri, autocommit=True, row_factory=dict_row)
        saver = PostgresSaver(conn)
        saver.setup()
        log.info("postgres checkpointer enabled")
        return saver
    except Exception:
        log.exception("checkpointer setup failed — continuing with in-memory state")
        return None


class PMAgent:
    def __init__(self, js, gitea: GiteaClient, checkpointer):
        self.js = js
        self.gitea = gitea
        self.checkpointer = checkpointer

    # ------------------------------------------------------------- dispatch

    async def dispatch(self, task: Task) -> None:
        task.status = TaskStatus.READY
        await bus.save_task(self.js, task)
        await bus.publish(self.js, bus.SUBJECT_READY, task)
        log.info("dispatched task %s (project %s)", task.task_id, task.project_id)

    async def dispatch_newly_ready(self, project_id: str) -> None:
        tasks = await bus.load_project_tasks(self.js, project_id)
        done = {t.task_id for t in tasks if t.status == TaskStatus.DONE}
        for t in tasks:
            if t.status == TaskStatus.PENDING and set(t.depends_on) <= done:
                await self.dispatch(t)

    async def escalate(self, task: Task, reason: str) -> None:
        """Bounded retries exhausted -> a human takes over with full context (risk of
        infinite loops; escalation is a feature, not a failure)."""
        task.status = TaskStatus.ESCALATED
        await bus.save_task(self.js, task)
        body = (
            f"The fleet could not complete this task after {task.attempts} attempt(s).\n\n"
            f"**Reason:** {reason}\n\n**Spec:**\n{task.spec}\n\n"
            f"**Acceptance criteria:**\n- " + "\n- ".join(task.acceptance_criteria) + "\n\n"
            f"**Last error:**\n```\n{task.last_error[:2000]}\n```\n\n"
            f"correlation_id: `{task.correlation_id}`"
        )
        try:
            issue = await asyncio.to_thread(
                self.gitea.create_issue, task.repo, f"[escalation] {task.title}", body
            )
            log.warning("escalated task %s -> issue #%d", task.task_id, issue)
        except Exception:
            log.exception("failed to create escalation issue for %s", task.task_id)
        await bus.publish_event(self.js, AgentEvent(
            event_type=EventType.ESCALATION,
            project_id=task.project_id,
            task_id=task.task_id,
            agent=settings.agent_name,
            correlation_id=task.correlation_id,
            payload={"reason": reason},
        ))

    # ---------------------------------------------------------------- briefs

    async def handle_brief(self, msg: Msg) -> None:
        brief = ProjectBrief.model_validate_json(msg.data)
        tracing.correlation_id.set(brief.correlation_id)
        log.info("brief received: %s", brief.project_id)
        try:
            await bus.save_brief(self.js, brief)

            if not await asyncio.to_thread(self.gitea.repo_exists, brief.project_id):
                await asyncio.to_thread(self.gitea.create_repo_from_template, brief.project_id)
                await asyncio.to_thread(self.gitea.protect_main, brief.project_id)

            tasks = await asyncio.to_thread(
                decompose_brief, settings, brief, self.checkpointer
            )
            log.info("decomposed into %d tasks: %s", len(tasks), [t.task_id for t in tasks])

            for t in tasks:
                await bus.save_task(self.js, t)
            for t in tasks:
                if not t.depends_on:
                    await self.dispatch(t)
            await msg.ack()
        except Exception as exc:
            log.exception("brief %s failed", brief.project_id)
            # Poison-message guard: don't redeliver forever; leave a trace for a human.
            try:
                if await asyncio.to_thread(self.gitea.repo_exists, brief.project_id):
                    await asyncio.to_thread(
                        self.gitea.create_issue, brief.project_id,
                        f"[escalation] brief processing failed: {brief.title}",
                        f"```\n{exc}\n```\ncorrelation_id: `{brief.correlation_id}`",
                    )
            finally:
                await msg.term()

    # ---------------------------------------------------------------- events

    async def handle_event(self, msg: Msg) -> None:
        ev = AgentEvent.model_validate_json(msg.data)
        tracing.correlation_id.set(ev.correlation_id or "-")
        try:
            match ev.event_type:
                case EventType.TASK_FAILED:
                    await self.on_task_failed(ev)
                case EventType.PR_MERGED:
                    await self.on_pr_merged(ev)
                case EventType.PR_REVIEWED:
                    await self.on_pr_reviewed(ev)
                case _:
                    pass  # not the PM's concern
        except Exception:
            log.exception("event handling failed: %s", ev.event_type)
        finally:
            await msg.ack()

    async def on_task_failed(self, ev: AgentEvent) -> None:
        task = await bus.load_task(self.js, ev.project_id, ev.task_id)
        if task is None:
            return
        if task.attempts >= settings.max_task_attempts:
            await self.escalate(task, f"failed {task.attempts} times")
        else:
            log.info("retrying task %s (attempt %d)", task.task_id, task.attempts + 1)
            await self.dispatch(task)

    async def on_pr_merged(self, ev: AgentEvent) -> None:
        task = await bus.load_task(self.js, ev.project_id, ev.task_id)
        if task is None:
            return
        task.status = TaskStatus.DONE
        await bus.save_task(self.js, task)
        log.info("task %s DONE (PR #%s merged)", task.task_id, ev.payload.get("pr_number"))

        tasks = await bus.load_project_tasks(self.js, ev.project_id)
        if all(t.status == TaskStatus.DONE for t in tasks):
            log.info("project %s COMPLETE", ev.project_id)
            await bus.publish_event(self.js, AgentEvent(
                event_type=EventType.PROJECT_DONE,
                project_id=ev.project_id,
                agent=settings.agent_name,
                correlation_id=ev.correlation_id,
            ))
        else:
            await self.dispatch_newly_ready(ev.project_id)

    async def on_pr_reviewed(self, ev: AgentEvent) -> None:
        if ev.payload.get("verdict") != "REQUEST_CHANGES":
            return  # approved: waiting on the human merge gate
        task = await bus.load_task(self.js, ev.project_id, ev.task_id)
        if task is None:
            return
        task.attempts += 1
        feedback = ev.payload.get("feedback", "")
        if task.attempts >= settings.max_task_attempts:
            await self.escalate(task, "reviewer rejected and retry budget exhausted")
            return
        task.spec += f"\n\n## Reviewer feedback (address all points)\n{feedback}"
        await bus.save_task(self.js, task)
        if task.pr_number:
            try:
                await asyncio.to_thread(
                    self.gitea.comment_pr, task.repo, task.pr_number,
                    "Superseded: the PM re-dispatched this task with the review feedback; a new PR will follow.",
                )
            except Exception:
                log.exception("could not comment superseded PR")
        await self.dispatch(task)


async def consume(js, sub, handler):
    while True:
        try:
            msgs = await sub.fetch(1, timeout=30)
        except TimeoutError:
            continue
        except Exception:
            log.exception("fetch failed; retrying in 5s")
            await asyncio.sleep(5)
            continue
        for m in msgs:
            await handler(m)


async def main() -> None:
    tracing.setup("pm-agent", settings.otel_endpoint)
    nc, js = await bus.connect(settings.nats_url)
    agent = PMAgent(js, GiteaClient(settings), make_checkpointer())

    briefs = await js.pull_subscribe(bus.SUBJECT_BRIEFS, durable="pm-briefs", stream=bus.STREAM_TASKS)
    events = await js.pull_subscribe("events.>", durable="pm-events", stream=bus.STREAM_EVENTS)

    log.info("pm-agent up (model=%s, max_attempts=%d)", settings.model, settings.max_task_attempts)
    try:
        await asyncio.gather(
            consume(js, briefs, agent.handle_brief),
            consume(js, events, agent.handle_event),
        )
    finally:
        await nc.drain()


if __name__ == "__main__":
    asyncio.run(main())
