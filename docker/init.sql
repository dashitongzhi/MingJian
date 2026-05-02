-- PlanAgent PostgreSQL initialization
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Pre-create alembic_version with wider column for long revision IDs
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(64) NOT NULL
);
