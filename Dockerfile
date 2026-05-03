FROM python:3.12-slim AS base

ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG http_proxy=""
ARG https_proxy=""
ARG NO_PROXY=""
ARG no_proxy=""
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""
ENV http_proxy=""
ENV https_proxy=""

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY rules ./rules
COPY migrations ./migrations
COPY examples ./examples
COPY alembic.ini ./

RUN pip install --no-cache-dir .

RUN groupadd --system appuser \
    && useradd --system --gid appuser --home-dir /home/appuser --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/source_snapshots \
    && chown -R appuser:appuser /app/source_snapshots \
    && chmod -R a+rX /app

FROM base AS api

USER appuser
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=5).read()" || exit 1
CMD ["planagent-api"]

FROM base AS worker

COPY scripts/start-workers.sh /app/start-workers.sh
RUN chmod +x /app/start-workers.sh

USER appuser
CMD ["/app/start-workers.sh"]
