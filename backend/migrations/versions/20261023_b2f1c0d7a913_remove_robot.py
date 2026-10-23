"""Remove o robô local (agente Playwright): fila de tarefas e sessão do navegador (ADR-020).

Revision ID: b2f1c0d7a913
Revises: 7434e1400df1
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2f1c0d7a913"
down_revision: str | None = "7434e1400df1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(op.f("ix_agent_job_status"), table_name="agent_job")
    op.drop_index(op.f("ix_agent_job_kind"), table_name="agent_job")
    op.drop_index(op.f("ix_agent_job_application_id"), table_name="agent_job")
    op.drop_table("agent_job")
    op.drop_table("browser_session_meta")
    # chaves de configuração que só o robô usava
    op.execute("DELETE FROM setting WHERE key IN ('limits', 'agent_control')")


def downgrade() -> None:
    op.create_table(
        "browser_session_meta",
        sa.Column("site", sa.Text(), nullable=False),
        sa.Column("last_login_ok_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_safety_stop_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_browser_session_meta")),
        sa.UniqueConstraint("site", name=op.f("uq_browser_session_meta_site")),
    )
    op.create_table(
        "agent_job",
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("priority", sa.Double(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifacts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"], ["application.id"], name=op.f("fk_agent_job_application_id_application"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_job")),
    )
    op.create_index(op.f("ix_agent_job_application_id"), "agent_job", ["application_id"], unique=False)
    op.create_index(op.f("ix_agent_job_kind"), "agent_job", ["kind"], unique=False)
    op.create_index(op.f("ix_agent_job_status"), "agent_job", ["status"], unique=False)
