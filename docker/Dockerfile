FROM python:3.10-slim

LABEL purpose="MindshardAGENT sandbox container"

# Common useful packages for agent tasks
RUN apt-get update && apt-get install -y --no-install-recommends \
    tree \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /sandbox

# Keep the container alive — we'll docker exec into it
CMD ["tail", "-f", "/dev/null"]
