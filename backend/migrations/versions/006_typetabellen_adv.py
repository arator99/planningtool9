"""Typetabellen en ADV-toekenningen (Fase 8).

Revision ID: 006_typetabellen_adv
Revises: 005_notities_mailbox
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa


revision = "006_typetabellen_adv"
down_revision = "005_notities_mailbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── typetabellen ───────────────────────────────────────────────────
    op.create_table(
        "typetabellen",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("locatie_id", sa.Integer(), sa.ForeignKey("locaties.id"), nullable=False),
        sa.Column("naam", sa.String(100), nullable=False),
        sa.Column("beschrijving", sa.Text(), nullable=True),
        sa.Column("aantal_weken", sa.Integer(), nullable=False),
        sa.Column("is_actief", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("aangemaakt_door_id", sa.Integer(), sa.ForeignKey("gebruikers.id"), nullable=False),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("gewijzigd_op", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("verwijderd_op", sa.DateTime(), nullable=True),
        sa.Column("verwijderd_door_id", sa.Integer(), nullable=True),
        sa.UniqueConstraint("locatie_id", "naam", name="uq_typetabel_locatie_naam"),
    )
    op.create_index("ix_typetabellen_locatie_id", "typetabellen", ["locatie_id"])
    op.create_index("ix_typetabellen_uuid", "typetabellen", ["uuid"])

    # ── typetabel_entries ──────────────────────────────────────────────
    op.create_table(
        "typetabel_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("typetabel_id", sa.Integer(), sa.ForeignKey("typetabellen.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_nummer", sa.Integer(), nullable=False),
        sa.Column("dag_van_week", sa.Integer(), nullable=False),
        sa.Column("shift_code", sa.String(20), nullable=True),
        sa.UniqueConstraint("typetabel_id", "week_nummer", "dag_van_week", name="uq_entry_week_dag"),
    )
    op.create_index("ix_typetabel_entries_typetabel_id", "typetabel_entries", ["typetabel_id"])

    # ── adv_toekenningen ──────────────────────────────────────────────
    op.create_table(
        "adv_toekenningen",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("gebruiker_id", sa.Integer(), sa.ForeignKey("gebruikers.id"), nullable=False),
        sa.Column("adv_type", sa.String(20), nullable=False),
        sa.Column("dag_van_week", sa.Integer(), nullable=True),
        sa.Column("start_datum", sa.Date(), nullable=False),
        sa.Column("eind_datum", sa.Date(), nullable=True),
        sa.Column("is_actief", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("aangemaakt_door_id", sa.Integer(), sa.ForeignKey("gebruikers.id"), nullable=False),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("gewijzigd_op", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("verwijderd_op", sa.DateTime(), nullable=True),
        sa.Column("verwijderd_door_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_adv_toekenningen_gebruiker_id", "adv_toekenningen", ["gebruiker_id"])
    op.create_index("ix_adv_toekenningen_uuid", "adv_toekenningen", ["uuid"])


def downgrade() -> None:
    op.drop_table("adv_toekenningen")
    op.drop_table("typetabel_entries")
    op.drop_table("typetabellen")
