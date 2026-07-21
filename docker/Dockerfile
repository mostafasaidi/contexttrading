# syntax=docker/dockerfile:1
# Multi-stage build for the ContextTrading engine + REST API.

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

EXPOSE 8000
CMD ["uvicorn", "contexttrading.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
