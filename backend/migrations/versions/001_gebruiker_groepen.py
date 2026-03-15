"""Voeg gebruiker_groepen junction table toe voor multi-team ondersteuning.

Revision ID: 001
Revises: —
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gebruiker_groepen",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "gebruiker_id",
            sa.Integer(),
            sa.ForeignKey("gebruikers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "groep_id",
            sa.Integer(),
            sa.ForeignKey("groepen.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("is_reserve", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("aangemaakt_op", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("gebruiker_id", "groep_id", name="uq_gebruiker_groep"),
    )

    # Populeer vanuit bestaande gebruikers.groep_id
    op.execute(
        """
        INSERT INTO gebruiker_groepen (gebruiker_id, groep_id, is_reserve)
        SELECT id, groep_id, false
        FROM gebruikers
        WHERE groep_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_table("gebruiker_groepen")
