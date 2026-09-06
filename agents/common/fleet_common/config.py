"""Agent configuration — everything comes from the environment (ConfigMap + Secrets)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLEET_", extra="ignore")

    agent_name: str = "agent"

    # Messaging
    nats_url: str = "nats://nats.fleet-core.svc.cluster.local:4222"

    # LLM gateway — the agent only ever sees its own virtual key (risk #5)
    litellm_base_url: str = "http://litellm.fleet-core.svc.cluster.local:4000"
    litellm_api_key: str = ""
    model: str = "claude-sonnet"
    small_model: str = "claude-haiku"

    # Git
    gitea_url: str = "http://gitea-http.fleet-git.svc.cluster.local:3000"
    gitea_org: str = "agents"
    gitea_user: str = ""
    gitea_token: str = ""
    webhook_secret: str = ""
    template_repo: str = "project-template"

    # Durability
    checkpoint_db_uri: str = ""  # postgresql://... (agentstate on Patroni); empty = in-memory

    # Bounds (risk #2 / runaway loops)
    max_iterations: int = 40         # LangGraph recursion limit per task
    max_task_attempts: int = 2       # retries before the PM escalates (risk of infinite loops)
    max_project_tasks: int = 8       # PM decomposition ceiling
    command_timeout_s: int = 300     # per shell command inside the dev agent

    work_dir: str = "/work"

    # Observability (optional OTLP endpoint; empty = local logging only)
    otel_endpoint: str = ""


settings = Settings()
