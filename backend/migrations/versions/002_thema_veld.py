"""Hernoem theme_voorkeur naar thema, default naar 'systeem'.

Revision ID: 002
Revises: 001
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("gebruikers", "theme_voorkeur", new_column_name="thema")
    op.alter_column(
        "gebruikers", "thema",
        existing_type=sa.String(10),
        server_default="systeem",
    )
    # Migreer bestaande waarden: 'light' en 'dark' blijven geldig; rest → 'systeem'
    op.execute(
        "UPDATE gebruikers SET thema = 'systeem' WHERE thema NOT IN ('light', 'dark', 'systeem')"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE gebruikers SET thema = 'light' WHERE thema = 'systeem'"
    )
    op.alter_column("gebruikers", "thema", new_column_name="theme_voorkeur")
    op.alter_column(
        "gebruikers", "theme_voorkeur",
        existing_type=sa.String(10),
        server_default="light",
    )
