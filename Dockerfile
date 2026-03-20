FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY rules ./rules
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir .

CMD ["planagent-api"]
