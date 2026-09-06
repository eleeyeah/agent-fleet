# Build context = agents/ (see build-images.sh)
ARG BASE_IMAGE=fleet-base:0.1.0
FROM ${BASE_IMAGE}

COPY pm/app/ /app/
CMD ["python", "/app/main.py"]
