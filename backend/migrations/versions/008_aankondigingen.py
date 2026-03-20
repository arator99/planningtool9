"""Aankondigingen tabel: sjabloon-gebaseerd i.p.v. vrije tekst.

Revision ID: 008_aankondigingen
Revises: 007_scherm_rechten
Create Date: 2026-03-20
"""
import sqlalchemy as sa
from alembic import op

revision = "008_aankondigingen"
down_revision = "007_scherm_rechten"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tabel aanmaken of aanpassen, afhankelijk van of hij al bestaat via create_all
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    bestaande_tabellen = inspector.get_table_names()

    if "aankondigingen" in bestaande_tabellen:
        # Tabel bestaat al (aangemaakt door create_all met oud schema)
        # Kolommen toevoegen als ze nog niet bestaan
        bestaande_kolommen = {k["name"] for k in inspector.get_columns("aankondigingen")}
        if "sjabloon" not in bestaande_kolommen:
            op.add_column(
                "aankondigingen",
                sa.Column("sjabloon", sa.String(50), nullable=False, server_default="onderhoud_gepland"),
            )
        if "extra_info" not in bestaande_kolommen:
            op.add_column(
                "aankondigingen",
                sa.Column("extra_info", sa.Text, nullable=True),
            )
        # Oude vrije-tekst kolommen verwijderen als ze nog bestaan
        if "titel" in bestaande_kolommen:
            op.drop_column("aankondigingen", "titel")
        if "bericht" in bestaande_kolommen:
            op.drop_column("aankondigingen", "bericht")
    else:
        op.create_table(
            "aankondigingen",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("uuid", sa.String(36), unique=True, nullable=False),
            sa.Column("sjabloon", sa.String(50), nullable=False, server_default="onderhoud_gepland"),
            sa.Column("extra_info", sa.Text, nullable=True),
            sa.Column("ernst", sa.String(20), nullable=False, server_default="info"),
            sa.Column("type", sa.String(20), nullable=False, server_default="banner"),
            sa.Column("gepland_van", sa.DateTime, nullable=True),
            sa.Column("gepland_tot", sa.DateTime, nullable=True),
            sa.Column("is_actief", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("aangemaakt_door_id", sa.Integer, sa.ForeignKey("gebruikers.id"), nullable=True),
            sa.Column("aangemaakt_op", sa.DateTime, nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("aankondigingen")
