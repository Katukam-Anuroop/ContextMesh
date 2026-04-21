FROM python:3.12-slim

LABEL maintainer="ContextSync <hello@contextsync.dev>"
LABEL description="ContextSync — Change Data Capture for AI-assisted codebases"

# Install git (required for GitPython)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Install contextsync
COPY . /app
WORKDIR /app
RUN pip install --no-cache-dir .

ENTRYPOINT ["contextsync"]
