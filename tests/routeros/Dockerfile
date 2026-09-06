# Developer-only isolated native RouterOS lab. Not an integration dependency.
FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends qemu-system-x86 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir aiohttp==3.12.15
WORKDIR /work
ENTRYPOINT ["python", "/work/tests/routeros/smoke.py"]
