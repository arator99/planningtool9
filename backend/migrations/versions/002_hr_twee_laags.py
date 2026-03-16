"""HR twee-laags: NationaleHRRegel + LocatieHROverride vervangt hr_regels.

Revision ID: 002
Revises: 001
Create Date: 2026-03-16
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Verwijder de tijdelijke hr_regels tabel (aangemaakt in 001)
    op.drop_table("hr_regels")

    # ------------------------------------------------------------------ #
    # Nationale HR-regels (super_beheerder beheer)                        #
    # ------------------------------------------------------------------ #
    op.create_table(
        "nationale_hr_regels",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("code", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("naam", sa.String(100), nullable=False),
        sa.Column("waarde", sa.Integer(), nullable=False),
        sa.Column("eenheid", sa.String(20), nullable=True),
        sa.Column("ernst_niveau", sa.String(20), nullable=False, server_default="WARNING"),
        sa.Column("richting", sa.String(3), nullable=False, server_default="max"),
        sa.Column("beschrijving", sa.Text(), nullable=True),
        sa.Column("is_actief", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("gewijzigd_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------ #
    # Locatie HR-overrides (beheerder per locatie)                        #
    # ------------------------------------------------------------------ #
    op.create_table(
        "locatie_hr_overrides",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "nationale_regel_id",
            sa.Integer(),
            sa.ForeignKey("nationale_hr_regels.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "locatie_id",
            sa.Integer(),
            sa.ForeignKey("locaties.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("waarde", sa.Integer(), nullable=False),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("gewijzigd_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("nationale_regel_id", "locatie_id", name="uq_override_regel_locatie"),
    )


def downgrade() -> None:
    op.drop_table("locatie_hr_overrides")
    op.drop_table("nationale_hr_regels")

    # Herstel tijdelijke hr_regels tabel
    op.create_table(
        "hr_regels",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("locatie_id", sa.Integer(), sa.ForeignKey("locaties.id"), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False, index=True),
        sa.Column("naam", sa.String(100), nullable=False),
        sa.Column("waarde", sa.Integer(), nullable=True),
        sa.Column("waarde_extra", sa.String(50), nullable=True),
        sa.Column("eenheid", sa.String(20), nullable=True),
        sa.Column("ernst_niveau", sa.String(20), nullable=False, server_default="WARNING"),
        sa.Column("is_actief", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("beschrijving", sa.Text(), nullable=True),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("gewijzigd_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
