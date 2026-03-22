"""GebruikerRol soft-delete kolommen: verwijderd_op + verwijderd_door_id.

Nodig voor het bijhouden van teamovergangen: ex-leden blijven zichtbaar
in het historisch planninggrid van het oude team.

Revision ID: 009_gebruikerrol_soft_delete
Revises: 008_aankondigingen
Create Date: 2026-03-22
"""
import sqlalchemy as sa
from alembic import op

revision = "009_gebruikerrol_soft_delete"
down_revision = "008_aankondigingen"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gebruiker_rollen", sa.Column("verwijderd_op", sa.DateTime(), nullable=True))
    op.add_column("gebruiker_rollen", sa.Column("verwijderd_door_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("gebruiker_rollen", "verwijderd_door_id")
    op.drop_column("gebruiker_rollen", "verwijderd_op")
