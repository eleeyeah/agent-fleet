"""NATS JetStream helpers.

Streams (created idempotently by every agent on startup):
  TASKS  (work-queue retention)  tasks.briefs  — consumed once by the PM
                                 tasks.ready   — consumed once by a dev agent
  EVENTS (limits retention)      events.>      — fan-out; PM and reviewer keep
                                                 independent durable consumers
KV bucket `task-state` holds the authoritative Task/ProjectBrief records keyed by
`task.<project>.<task_id>` / `brief.<project>` so any agent can be restarted and
re-read state (agents themselves stay stateless).
"""

from __future__ import annotations

import logging

import nats
from nats.js import JetStreamContext
from nats.js.api import KeyValueConfig, RetentionPolicy, StreamConfig
from nats.js.errors import BadRequestError, NotFoundError
from pydantic import BaseModel

from .models import AgentEvent, ProjectBrief, Task

log = logging.getLogger(__name__)

STREAM_TASKS = "TASKS"
STREAM_EVENTS = "EVENTS"
KV_TASK_STATE = "task-state"

SUBJECT_BRIEFS = "tasks.briefs"
SUBJECT_READY = "tasks.ready"
SUBJECT_EVENTS_PREFIX = "events"  # events.<event_type>

ONE_WEEK_S = 7 * 24 * 3600


async def connect(nats_url: str) -> tuple[nats.NATS, JetStreamContext]:
    nc = await nats.connect(nats_url, max_reconnect_attempts=-1)
    js = nc.jetstream()
    await ensure_streams(js)
    return nc, js


async def ensure_streams(js: JetStreamContext) -> None:
    for cfg in (
        StreamConfig(
            name=STREAM_TASKS,
            subjects=["tasks.>"],
            retention=RetentionPolicy.WORK_QUEUE,
            max_age=ONE_WEEK_S,
        ),
        StreamConfig(
            name=STREAM_EVENTS,
            subjects=["events.>"],
            retention=RetentionPolicy.LIMITS,
            max_age=ONE_WEEK_S,
        ),
    ):
        try:
            await js.add_stream(cfg)
        except BadRequestError:
            # Stream exists (possibly with equivalent config) — fine.
            pass
    try:
        await js.key_value(KV_TASK_STATE)
    except NotFoundError:
        await js.create_key_value(KeyValueConfig(bucket=KV_TASK_STATE))


async def publish(js: JetStreamContext, subject: str, model: BaseModel) -> None:
    await js.publish(subject, model.model_dump_json().encode())


async def publish_event(js: JetStreamContext, event: AgentEvent) -> None:
    await publish(js, f"{SUBJECT_EVENTS_PREFIX}.{event.event_type}", event)
    log.info(
        "event %s project=%s task=%s cid=%s",
        event.event_type, event.project_id, event.task_id, event.correlation_id,
    )


# --------------------------------------------------------------- task state KV

async def kv_bucket(js: JetStreamContext):
    return await js.key_value(KV_TASK_STATE)


async def save_task(js: JetStreamContext, task: Task) -> None:
    kv = await kv_bucket(js)
    await kv.put(task.kv_key, task.model_dump_json().encode())


async def load_task(js: JetStreamContext, project_id: str, task_id: str) -> Task | None:
    kv = await kv_bucket(js)
    try:
        entry = await kv.get(f"task.{project_id}.{task_id}")
    except Exception:
        return None
    return Task.model_validate_json(entry.value)


async def load_project_tasks(js: JetStreamContext, project_id: str) -> list[Task]:
    kv = await kv_bucket(js)
    tasks: list[Task] = []
    try:
        keys = await kv.keys()
    except Exception:
        return tasks
    prefix = f"task.{project_id}."
    for key in keys:
        if key.startswith(prefix):
            entry = await kv.get(key)
            tasks.append(Task.model_validate_json(entry.value))
    return tasks


async def save_brief(js: JetStreamContext, brief: ProjectBrief) -> None:
    kv = await kv_bucket(js)
    await kv.put(f"brief.{brief.project_id}", brief.model_dump_json().encode())
