"""reviewer agent: two responsibilities.

1. NATS consumer on events.pr_opened -> fetch the diff, review against acceptance
   criteria, post APPROVED / REQUEST_CHANGES on the PR, publish events.pr_reviewed.
2. HTTP webhook receiver for Gitea (HMAC-verified): when a human merges a task PR,
   publish events.pr_merged so the PM can advance the DAG.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from nats.aio.msg import Msg

from fleet_common import bus, tracing
from fleet_common.config import settings
from fleet_common.gitea import GiteaClient
from fleet_common.models import AgentEvent, EventType
from review import format_review, review_pr

log = logging.getLogger("reviewer")

app = FastAPI()
_js = None  # set in main()


def parse_task_branch(branch: str) -> str | None:
    """task/<task_id>-a<attempt> -> task_id (None for non-fleet branches)."""
    if not branch.startswith("task/"):
        return None
    rest = branch.removeprefix("task/")
    head, sep, tail = rest.rpartition("-a")
    return head if sep and tail.isdigit() else None


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.post("/webhook/gitea")
async def gitea_webhook(request: Request, x_gitea_signature: str = Header(default="")):
    body = await request.body()
    expected = hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not settings.webhook_secret or not hmac.compare_digest(expected, x_gitea_signature):
        raise HTTPException(status_code=403, detail="bad signature")

    payload = await request.json()
    pr = payload.get("pull_request") or {}
    action = payload.get("action", "")
    branch = (pr.get("head") or {}).get("ref", "")
    task_id = parse_task_branch(branch)
    if task_id is None:
        return {"ignored": "not a fleet branch"}

    # The human merge gate fired: tell the PM.
    if action == "closed" and pr.get("merged"):
        repo = (payload.get("repository") or {}).get("name", "")
        task = await bus.load_task(_js, repo, task_id)
        await bus.publish_event(_js, AgentEvent(
            event_type=EventType.PR_MERGED,
            project_id=repo,
            task_id=task_id,
            agent=settings.agent_name,
            correlation_id=task.correlation_id if task else "",
            payload={"pr_number": pr.get("number"), "branch": branch},
        ))
        return {"published": "pr_merged"}
    return {"ignored": action}


async def handle_pr_opened(js, gitea: GiteaClient, msg: Msg) -> None:
    ev = AgentEvent.model_validate_json(msg.data)
    tracing.correlation_id.set(ev.correlation_id or "-")
    try:
        task = await bus.load_task(js, ev.project_id, ev.task_id)
        pr_number = ev.payload.get("pr_number")
        if task is None or pr_number is None:
            log.warning("pr_opened without task/pr context: %s", ev.payload)
            return

        diff = await asyncio.to_thread(gitea.get_pr_diff, task.repo, pr_number)
        verdict = await asyncio.to_thread(review_pr, settings, task, diff)
        log.info("PR #%s (%s): %s", pr_number, task.task_id, verdict.verdict)

        await asyncio.to_thread(
            gitea.create_review, task.repo, pr_number,
            verdict.verdict, format_review(verdict, task),
        )
        await bus.publish_event(js, AgentEvent(
            event_type=EventType.PR_REVIEWED,
            project_id=ev.project_id,
            task_id=ev.task_id,
            agent=settings.agent_name,
            correlation_id=ev.correlation_id,
            payload={
                "pr_number": pr_number,
                "verdict": verdict.verdict,
                "feedback": format_review(verdict, task),
            },
        ))
    except Exception:
        log.exception("review failed for %s", ev.task_id)
    finally:
        await msg.ack()


async def consume_reviews(js, gitea: GiteaClient) -> None:
    sub = await js.pull_subscribe(
        f"{bus.SUBJECT_EVENTS_PREFIX}.{EventType.PR_OPENED}",
        durable="reviewer-prs",
        stream=bus.STREAM_EVENTS,
    )
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
            await handle_pr_opened(js, gitea, m)


async def main() -> None:
    global _js
    tracing.setup("reviewer-agent", settings.otel_endpoint)
    nc, _js = await bus.connect(settings.nats_url)
    gitea = GiteaClient(settings)

    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="warning"))
    log.info("reviewer up (model=%s)", settings.model)
    try:
        await asyncio.gather(server.serve(), consume_reviews(_js, gitea))
    finally:
        await nc.drain()


if __name__ == "__main__":
    asyncio.run(main())
