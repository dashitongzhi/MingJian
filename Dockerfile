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
COPY alembic.ini ./

RUN pip install --no-cache-dir .

FROM base AS api

CMD ["planagent-api"]

FROM base AS worker

COPY scripts/start-workers.sh /app/start-workers.sh
RUN chmod +x /app/start-workers.sh

CMD ["/app/start-workers.sh"]
