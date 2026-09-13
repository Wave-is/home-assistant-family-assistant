# Standalone Optional AGY CLI Gateway Dockerfile
ARG AGY_BASE_IMAGE=python:3.11-slim
FROM ${AGY_BASE_IMAGE}

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install runtime dependencies for the aiohttp gateway
RUN pip install --no-cache-dir aiohttp==3.12.15 Pillow==12.3.0 jsonschema==4.26.0

# Copy only public service code and explicit agent profiles
COPY services/agy_gateway/ /app/services/agy_gateway/

EXPOSE 8080

ENTRYPOINT ["python", "-m", "services.agy_gateway"]
