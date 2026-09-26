# The Eden API. Build context: the repo root.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependency layer, cached until requirements.txt changes.
COPY apps/api/requirements.txt .
RUN pip install -r requirements.txt

COPY apps/api/app ./app

# Unprivileged, the same uid every stack on the VPS uses.
RUN useradd --create-home --uid 10001 appuser
USER appuser

ARG GIT_SHA=dev
ENV GIT_SHA=$GIT_SHA

EXPOSE 8000
# `python -m app` refuses to start on unsafe production settings, then runs uvicorn.
CMD ["python", "-m", "app"]
