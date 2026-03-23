"""Lidmaatschap + Area refactor — vervangt GebruikerRol teamlid/planner door Lidmaatschap tabel.

Wijzigingen:
- Nieuw: tabel `areas`
- Nieuw: tabel `lidmaatschappen`
- `locaties`: voeg `area_id` toe (nullable FK → areas)
- `gebruikers`: verwijder `locatie_id`
- `gebruiker_rollen`:
    * voeg `scope_locatie_id` toe (nullable FK → locaties)
    * voeg `scope_area_id` toe (nullable FK → areas)
    * migreer data: teamlid/planner → lidmaatschappen
    * verwijder `scope_id` en `is_reserve` kolommen
    * pas enum aan: alleen super_beheerder | beheerder | hr
    * voeg UniqueConstraint + CheckConstraints toe

Revision ID: 010_lidmaatschap_area_refactor
Revises: 009_gebruikerrol_soft_delete
Create Date: 2026-03-23
"""
import uuid as uuid_module

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "010_lidmaatschap_area_refactor"
down_revision = "009_gebruikerrol_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------ #
    # 1. Maak `areas` tabel aan                                           #
    # ------------------------------------------------------------------ #
    op.create_table(
        "areas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("naam", sa.String(100), nullable=False, unique=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("is_actief", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("verwijderd_op", sa.DateTime(), nullable=True),
        sa.Column("verwijderd_door_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_areas_id", "areas", ["id"])

    # ------------------------------------------------------------------ #
    # 2. Voeg `area_id` toe aan `locaties`                                #
    # ------------------------------------------------------------------ #
    op.add_column(
        "locaties",
        sa.Column("area_id", sa.Integer(), sa.ForeignKey("areas.id", ondelete="RESTRICT"), nullable=True),
    )
    op.create_index("ix_locaties_area_id", "locaties", ["area_id"])

    # ------------------------------------------------------------------ #
    # 3. Maak `lidmaatschappen` tabel aan                                 #
    # ------------------------------------------------------------------ #
    op.create_table(
        "lidmaatschappen",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("gebruiker_id", sa.Integer(),
                  sa.ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.Integer(),
                  sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_planner", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("type", sa.String(20), nullable=False, server_default="Vast"),
        sa.Column("is_actief", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("verwijderd_op", sa.DateTime(), nullable=True),
        sa.Column("verwijderd_door_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_lidmaatschappen_id", "lidmaatschappen", ["id"])
    op.create_index("ix_lidmaatschappen_gebruiker_id", "lidmaatschappen", ["gebruiker_id"])
    op.create_index("ix_lidmaatschappen_team_id_actief", "lidmaatschappen", ["team_id"],
                    postgresql_where=text("is_actief = TRUE AND verwijderd_op IS NULL"))
    op.create_index("ix_lidmaatschappen_gebruiker_actief", "lidmaatschappen", ["gebruiker_id", "team_id"],
                    postgresql_where=text("is_actief = TRUE AND verwijderd_op IS NULL"))
    # Partial unique: staat re-activatie toe na soft-delete
    op.create_index("uq_lidmaatschap_actief", "lidmaatschappen", ["gebruiker_id", "team_id"],
                    unique=True,
                    postgresql_where=text("verwijderd_op IS NULL"))

    # ------------------------------------------------------------------ #
    # 4. Voeg `scope_locatie_id` en `scope_area_id` toe aan               #
    #    `gebruiker_rollen`                                                #
    # ------------------------------------------------------------------ #
    op.add_column(
        "gebruiker_rollen",
        sa.Column("scope_locatie_id", sa.Integer(),
                  sa.ForeignKey("locaties.id", ondelete="RESTRICT"), nullable=True),
    )
    op.add_column(
        "gebruiker_rollen",
        sa.Column("scope_area_id", sa.Integer(),
                  sa.ForeignKey("areas.id", ondelete="RESTRICT"), nullable=True),
    )
    op.create_index("ix_gebruiker_rollen_scope_locatie", "gebruiker_rollen", ["scope_locatie_id"])
    op.create_index("ix_gebruiker_rollen_scope_area", "gebruiker_rollen", ["scope_area_id"])

    # ------------------------------------------------------------------ #
    # 5. Migreer bestaande beheerder/hr scope_id → scope_locatie_id      #
    # ------------------------------------------------------------------ #
    conn.execute(text("""
        UPDATE gebruiker_rollen
        SET scope_locatie_id = scope_id
        WHERE rol IN ('beheerder', 'hr') AND scope_id IS NOT NULL
    """))

    # ------------------------------------------------------------------ #
    # 6. Migreer teamlid/planner rollen → lidmaatschappen                 #
    # ------------------------------------------------------------------ #
    rijen = conn.execute(text("""
        SELECT gr.gebruiker_id, gr.scope_id AS team_id,
               gr.rol, gr.is_reserve, gr.is_actief,
               gr.verwijderd_op, gr.verwijderd_door_id
        FROM gebruiker_rollen gr
        WHERE gr.rol IN ('teamlid', 'planner')
          AND gr.scope_id IS NOT NULL
        ORDER BY gr.gebruiker_id, gr.scope_id, gr.rol
    """)).fetchall()

    # Groepeer per (gebruiker_id, team_id) — planner wint boven teamlid
    leden: dict[tuple, dict] = {}
    for rij in rijen:
        sleutel = (rij.gebruiker_id, rij.team_id)
        bestaand = leden.get(sleutel)
        if bestaand is None:
            leden[sleutel] = dict(rij._mapping)
        elif rij.rol == "planner":
            # planner heeft hogere rechten, overschrijf
            leden[sleutel] = dict(rij._mapping)

    for (gebruiker_id, team_id), data in leden.items():
        is_planner = data["rol"] == "planner"
        lid_type = "Reserve" if data.get("is_reserve") else "Vast"
        conn.execute(text("""
            INSERT INTO lidmaatschappen
                (uuid, gebruiker_id, team_id, is_planner, type, is_actief,
                 verwijderd_op, verwijderd_door_id)
            VALUES
                (:uuid, :gebruiker_id, :team_id, :is_planner, :type, :is_actief,
                 :verwijderd_op, :verwijderd_door_id)
            ON CONFLICT DO NOTHING
        """), {
            "uuid": str(uuid_module.uuid4()),
            "gebruiker_id": gebruiker_id,
            "team_id": team_id,
            "is_planner": is_planner,
            "type": lid_type,
            "is_actief": data.get("is_actief", True),
            "verwijderd_op": data.get("verwijderd_op"),
            "verwijderd_door_id": data.get("verwijderd_door_id"),
        })

    # ------------------------------------------------------------------ #
    # 7. Verwijder teamlid/planner rollen uit `gebruiker_rollen`          #
    # ------------------------------------------------------------------ #
    conn.execute(text("""
        DELETE FROM gebruiker_rollen WHERE rol IN ('teamlid', 'planner')
    """))

    # ------------------------------------------------------------------ #
    # 8. Verwijder verouderde kolommen uit `gebruiker_rollen`             #
    # ------------------------------------------------------------------ #
    # Verwijder bestaande unique constraint + index (afhankelijk van scope_id)
    # Gebruik raw SQL met DO-block zodat een ontbrekende constraint geen fout geeft
    conn.execute(text("""
        DO $$
        BEGIN
            ALTER TABLE gebruiker_rollen DROP CONSTRAINT IF EXISTS uq_gebruiker_rol_scope_id;
            ALTER TABLE gebruiker_rollen DROP CONSTRAINT IF EXISTS uq_gebruiker_rol_scope;
        EXCEPTION WHEN OTHERS THEN NULL;
        END$$;
    """))

    op.drop_index("ix_gebruiker_rollen_scope_id", table_name="gebruiker_rollen", if_exists=True)
    op.drop_column("gebruiker_rollen", "scope_id")
    op.drop_column("gebruiker_rollen", "is_reserve")

    # ------------------------------------------------------------------ #
    # 9. Verwijder `locatie_id` uit `gebruikers`                          #
    # ------------------------------------------------------------------ #
    op.drop_index("ix_gebruikers_locatie_id", table_name="gebruikers", if_exists=True)
    op.drop_column("gebruikers", "locatie_id")

    # ------------------------------------------------------------------ #
    # 10. Voeg nieuwe UniqueConstraint + CheckConstraints toe              #
    # ------------------------------------------------------------------ #
    op.create_unique_constraint(
        "uq_gebruiker_rol_scope",
        "gebruiker_rollen",
        ["gebruiker_id", "rol", "scope_locatie_id", "scope_area_id"],
    )
    op.create_check_constraint(
        "chk_scope_combinatie",
        "gebruiker_rollen",
        "(rol = 'super_beheerder' AND scope_locatie_id IS NULL AND scope_area_id IS NULL)"
        " OR (rol = 'beheerder' AND scope_locatie_id IS NOT NULL AND scope_area_id IS NULL)"
        " OR (rol = 'hr' AND scope_locatie_id IS NULL)",
    )
    op.create_check_constraint(
        "chk_rol_geldig",
        "gebruiker_rollen",
        "rol IN ('super_beheerder', 'beheerder', 'hr')",
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Herstel `locatie_id` op `gebruikers` (leeg — data is weg)
    op.add_column("gebruikers", sa.Column("locatie_id", sa.Integer(), nullable=True))

    # Herstel `scope_id` en `is_reserve` op `gebruiker_rollen`
    op.add_column("gebruiker_rollen", sa.Column("scope_id", sa.Integer(), nullable=True))
    op.add_column("gebruiker_rollen", sa.Column("is_reserve", sa.Boolean(),
                                                 nullable=False, server_default="false"))

    # Herstel data: scope_locatie_id → scope_id voor beheerder/hr
    conn.execute(text("""
        UPDATE gebruiker_rollen
        SET scope_id = scope_locatie_id
        WHERE rol IN ('beheerder', 'hr')
    """))

    # Verwijder nieuwe constraints
    op.drop_constraint("chk_rol_geldig", "gebruiker_rollen", type_="check")
    op.drop_constraint("chk_scope_combinatie", "gebruiker_rollen", type_="check")
    op.drop_constraint("uq_gebruiker_rol_scope", "gebruiker_rollen", type_="unique")

    # Verwijder nieuwe kolommen
    op.drop_index("ix_gebruiker_rollen_scope_area", table_name="gebruiker_rollen")
    op.drop_index("ix_gebruiker_rollen_scope_locatie", table_name="gebruiker_rollen")
    op.drop_column("gebruiker_rollen", "scope_area_id")
    op.drop_column("gebruiker_rollen", "scope_locatie_id")

    # Verwijder `lidmaatschappen`
    op.drop_index("uq_lidmaatschap_actief", table_name="lidmaatschappen")
    op.drop_index("ix_lidmaatschappen_gebruiker_actief", table_name="lidmaatschappen")
    op.drop_index("ix_lidmaatschappen_team_id_actief", table_name="lidmaatschappen")
    op.drop_index("ix_lidmaatschappen_gebruiker_id", table_name="lidmaatschappen")
    op.drop_index("ix_lidmaatschappen_id", table_name="lidmaatschappen")
    op.drop_table("lidmaatschappen")

    # Verwijder `area_id` van `locaties`
    op.drop_index("ix_locaties_area_id", table_name="locaties")
    op.drop_column("locaties", "area_id")

    # Verwijder `areas`
    op.drop_index("ix_areas_id", table_name="areas")
    op.drop_table("areas")
