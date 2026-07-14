"""serialize recommendation version numbers per strategic session

Revision ID: 0028_recommendation_version_integrity
Revises: 0027_auth_token_version
Create Date: 2026-07-15 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


revision = "0028_recommendation_version_integrity"
down_revision = "0027_auth_token_version"
branch_labels = None
depends_on = None


_CONSTRAINT_NAME = "uq_recommendation_versions_session_version"
_CONSTRAINT_COLUMNS = {"session_id", "version_number"}


def _has_timeline_unique_constraint(bind: Connection) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table("recommendation_versions"):
        return False
    return any(
        set(constraint.get("column_names") or []) == _CONSTRAINT_COLUMNS
        for constraint in inspector.get_unique_constraints("recommendation_versions")
    )


def _renumber_existing_timelines(bind: Connection) -> None:
    rows = list(
        bind.execute(
            sa.text(
                "SELECT id, session_id, version_number "
                "FROM recommendation_versions "
                "ORDER BY session_id, generated_at, id"
            )
        ).mappings()
    )
    current_session_id: str | None = None
    used_version_numbers: set[int] = set()
    for row in rows:
        session_id = str(row["session_id"])
        if session_id != current_session_id:
            current_session_id = session_id
            used_version_numbers = set()
        version_number = int(row["version_number"])
        if version_number >= 1 and version_number not in used_version_numbers:
            used_version_numbers.add(version_number)
            continue
        version_number = max(used_version_numbers, default=0) + 1
        used_version_numbers.add(version_number)
        bind.execute(
            sa.text(
                "UPDATE recommendation_versions "
                "SET version_number = :version_number WHERE id = :record_id"
            ),
            {
                "version_number": version_number,
                "record_id": row["id"],
            },
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("recommendation_versions"):
        return
    if _has_timeline_unique_constraint(bind):
        return

    _renumber_existing_timelines(bind)
    with op.batch_alter_table("recommendation_versions") as batch_op:
        batch_op.create_unique_constraint(
            _CONSTRAINT_NAME,
            ["session_id", "version_number"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_timeline_unique_constraint(bind):
        return
    with op.batch_alter_table("recommendation_versions") as batch_op:
        batch_op.drop_constraint(_CONSTRAINT_NAME, type_="unique")
