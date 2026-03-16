"""UUID-velden: hernoem gebruiker_uuid → uuid; voeg uuid toe aan verlof_aanvragen,
nationale_hr_regels, notities en competenties.

Revision ID: 004
Revises: 003
Create Date: 2026-03-16
"""
import uuid

from alembic import op
import sqlalchemy as sa


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

# Helper: genereer uuid4-string voor bestaande records via SQL
_gen_uuid = "gen_random_uuid()::text"  # PostgreSQL 13+


def upgrade() -> None:
    # ── gebruikers: hernoem gebruiker_uuid → uuid ───────────────────
    op.alter_column("gebruikers", "gebruiker_uuid", new_column_name="uuid")

    # ── verlof_aanvragen: voeg uuid toe ─────────────────────────────
    op.add_column("verlof_aanvragen", sa.Column("uuid", sa.String(36), nullable=True))
    op.execute("UPDATE verlof_aanvragen SET uuid = gen_random_uuid()::text WHERE uuid IS NULL")
    op.alter_column("verlof_aanvragen", "uuid", nullable=False)
    op.create_unique_constraint("uq_verlof_aanvragen_uuid", "verlof_aanvragen", ["uuid"])

    # ── nationale_hr_regels: voeg uuid toe ──────────────────────────
    op.add_column("nationale_hr_regels", sa.Column("uuid", sa.String(36), nullable=True))
    op.execute("UPDATE nationale_hr_regels SET uuid = gen_random_uuid()::text WHERE uuid IS NULL")
    op.alter_column("nationale_hr_regels", "uuid", nullable=False)
    op.create_unique_constraint("uq_nationale_hr_regels_uuid", "nationale_hr_regels", ["uuid"])

    # ── notities: voeg uuid toe ─────────────────────────────────────
    op.add_column("notities", sa.Column("uuid", sa.String(36), nullable=True))
    op.execute("UPDATE notities SET uuid = gen_random_uuid()::text WHERE uuid IS NULL")
    op.alter_column("notities", "uuid", nullable=False)
    op.create_unique_constraint("uq_notities_uuid", "notities", ["uuid"])

    # ── competenties: voeg uuid toe ─────────────────────────────────
    op.add_column("competenties", sa.Column("uuid", sa.String(36), nullable=True))
    op.execute("UPDATE competenties SET uuid = gen_random_uuid()::text WHERE uuid IS NULL")
    op.alter_column("competenties", "uuid", nullable=False)
    op.create_unique_constraint("uq_competenties_uuid", "competenties", ["uuid"])


def downgrade() -> None:
    op.drop_constraint("uq_competenties_uuid", "competenties", type_="unique")
    op.drop_column("competenties", "uuid")

    op.drop_constraint("uq_notities_uuid", "notities", type_="unique")
    op.drop_column("notities", "uuid")

    op.drop_constraint("uq_nationale_hr_regels_uuid", "nationale_hr_regels", type_="unique")
    op.drop_column("nationale_hr_regels", "uuid")

    op.drop_constraint("uq_verlof_aanvragen_uuid", "verlof_aanvragen", type_="unique")
    op.drop_column("verlof_aanvragen", "uuid")

    op.alter_column("gebruikers", "uuid", new_column_name="gebruiker_uuid")
