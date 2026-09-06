# Build context = agents/ (see build-images.sh)
ARG BASE_IMAGE=fleet-base:0.1.0
FROM ${BASE_IMAGE}

# The dev agent runs project test suites in-pod
RUN pip install --no-cache-dir pytest==8.3.5

COPY backend-dev/app/ /app/
CMD ["python", "/app/main.py"]
