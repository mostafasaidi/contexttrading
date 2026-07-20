# syntax=docker/dockerfile:1
# Multi-stage build for the ContextTrading engine/API.
# NOTE: service wiring lands in later phases; this image packages the library
# and the (future) FastAPI entrypoint.

FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip wheel --no-cache-dir --no-deps -w /wheels .


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# Phase 9: expose the FastAPI app.
# EXPOSE 8000
# CMD ["uvicorn", "contexttrading.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
CMD ["python", "-c", "import contexttrading; print('contexttrading', contexttrading.__version__)"]
