# Shared base for all fleet agents. Build context = agents/ (see build-images.sh).
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 fleet

COPY base/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY common/ /opt/fleet-common/
RUN pip install --no-cache-dir /opt/fleet-common

# Git identity for commits made by agents (per-repo author is set at commit time)
USER fleet
RUN git config --global user.name "fleet-agent" \
    && git config --global user.email "fleet-agent@fleet.local" \
    && git config --global init.defaultBranch main

WORKDIR /app
