FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY app /app/app
COPY docs /app/docs
COPY monitoring /app/monitoring
COPY migrations /app/migrations
COPY scripts /app/scripts
COPY seed /app/seed
COPY alembic.ini /app/alembic.ini

RUN python -m pip install --upgrade pip \
    && python -m pip install -e .[dev]

RUN chmod +x /app/scripts/*.sh

EXPOSE 8000 9100

