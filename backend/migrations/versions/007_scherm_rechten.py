"""Scherm rechten tabel.

Revision ID: 007_scherm_rechten
Revises: 006_typetabellen_adv
Create Date: 2026-03-20
"""
import sqlalchemy as sa
from alembic import op

revision = "007_scherm_rechten"
down_revision = "006_typetabellen_adv"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scherm_rechten",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("route_naam", sa.String(100), nullable=False),
        sa.Column("rol", sa.String(50), nullable=False),
        sa.Column("locatie_id", sa.Integer, sa.ForeignKey("locaties.id"), nullable=True),
        sa.Column("toegestaan", sa.Boolean, nullable=False),
        sa.Column("aangemaakt_op", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scherm_rechten_route_naam", "scherm_rechten", ["route_naam"])
    op.create_index("ix_scherm_rechten_locatie_id", "scherm_rechten", ["locatie_id"])
    op.create_unique_constraint(
        "uq_schermrecht_route_rol_locatie",
        "scherm_rechten",
        ["route_naam", "rol", "locatie_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_scherm_rechten_locatie_id", table_name="scherm_rechten")
    op.drop_index("ix_scherm_rechten_route_naam", table_name="scherm_rechten")
    op.drop_table("scherm_rechten")
