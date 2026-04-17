# syntax=docker/dockerfile:1.7
#
# Multi-stage Dockerfile for Quot PSE.
#
# * ``builder`` installs Python dependencies into a virtualenv so the
#   final image doesn't carry compilers or apt caches.
# * ``runtime`` is a slim image with only the virtualenv, app code, and
#   the runtime dependencies needed by WeasyPrint (for PDF IPSAS exports)
#   and psycopg2.
#
# Build:   docker build -t quot-pse:latest .
# Run:     docker run --rm -p 8000:8000 --env-file .env quot-pse:latest
# Migrate: docker run --rm --env-file .env quot-pse:latest \
#            python manage.py migrate_schemas --shared
#
# IMPORTANT: this image runs as a non-root ``app`` user. Mount volumes
# into ``/app`` if you need live reload — and make sure the host-side
# permissions are readable by UID 1000.

# =============================================================================
# Stage 1 — builder
# =============================================================================
FROM python:3.12-slim AS builder

# Build deps only — purged in the runtime stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libffi-dev \
        libpangoft2-1.0-0 \
        libpango-1.0-0 \
        libharfbuzz0b \
        libjpeg-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Install Python deps into a dedicated virtualenv so we can copy the
# whole tree into the runtime stage without polluting system site-packages.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# =============================================================================
# Stage 2 — runtime
# =============================================================================
FROM python:3.12-slim AS runtime

# Runtime libraries required by psycopg2 + weasyprint. ``libpq5`` is the
# runtime half of ``libpq-dev`` from the builder stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libpangoft2-1.0-0 \
        libpango-1.0-0 \
        libharfbuzz0b \
        libjpeg62-turbo \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --create-home app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=quot_pse.settings

# Copy the virtualenv from the builder.
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Copy the application tree. ``.dockerignore`` keeps tests, docs, and
# debug scripts out of the runtime image.
COPY --chown=app:app . /app

USER app

EXPOSE 8000

# Default: run Django via gunicorn-style entrypoint. For dev, override
# with ``python manage.py runserver 0.0.0.0:8000`` via docker-compose.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
