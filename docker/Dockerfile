# syntax=docker/dockerfile:1
# Multi-stage build for the ContextTrading engine + REST API.
# Builder compiles a wheel; runtime installs it with the 'api' extra,
# runs as a non-root user, and health-checks /healthz.

FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip wheel --no-cache-dir -w /wheels ".[api]"


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Non-root runtime user.
RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# SQLite result store lives here in the default compose wiring (named
# volume); owned by the runtime user.
RUN mkdir -p /data && chown app:app /data
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

CMD ["uvicorn", "contexttrading.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
