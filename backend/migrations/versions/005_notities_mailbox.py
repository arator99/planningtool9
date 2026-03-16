"""Notities: vervang team_id door mailboxhiërarchie (naar_rol, naar_scope_id, locatie_id).

Revision ID: 005_notities_mailbox
Revises: 004
Create Date: 2026-03-16
"""
from alembic import op
import sqlalchemy as sa


revision = "005_notities_mailbox"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── notities: voeg nieuwe kolommen toe ─────────────────────────
    op.add_column("notities", sa.Column("locatie_id", sa.Integer(), nullable=True))
    op.add_column("notities", sa.Column("naar_rol", sa.String(30), nullable=True))
    op.add_column("notities", sa.Column("naar_scope_id", sa.Integer(), nullable=True))

    # Index op nieuwe kolommen
    op.create_index("ix_notities_locatie_id", "notities", ["locatie_id"])
    op.create_index("ix_notities_naar_rol", "notities", ["naar_rol"])
    op.create_index("ix_notities_naar_scope_id", "notities", ["naar_scope_id"])

    # ── notities: verwijder team_id kolom ────────────────────────────
    # Eerst eventuele FK constraint droppen (naam kan variëren per DB)
    try:
        op.drop_constraint("notities_team_id_fkey", "notities", type_="foreignkey")
    except Exception:
        pass  # constraint bestaat niet of heeft andere naam

    try:
        op.drop_index("ix_notities_team_id", table_name="notities")
    except Exception:
        pass

    op.drop_column("notities", "team_id")

    # planning_datum kolom was optioneel — verwijder ook als aanwezig
    try:
        op.drop_column("notities", "planning_datum")
    except Exception:
        pass


def downgrade() -> None:
    # Voeg team_id terug toe
    op.add_column("notities", sa.Column("team_id", sa.Integer(), nullable=True))

    # Verwijder nieuwe kolommen
    op.drop_index("ix_notities_naar_scope_id", table_name="notities")
    op.drop_index("ix_notities_naar_rol", table_name="notities")
    op.drop_index("ix_notities_locatie_id", table_name="notities")
    op.drop_column("notities", "naar_scope_id")
    op.drop_column("notities", "naar_rol")
    op.drop_column("notities", "locatie_id")
