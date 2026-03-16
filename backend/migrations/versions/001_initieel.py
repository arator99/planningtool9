"""Initieel schema v0.9 — Locatie/Team/GebruikerRol architectuur.

Revision ID: 001
Revises:
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # Locaties                                                             #
    # ------------------------------------------------------------------ #
    op.create_table(
        "locaties",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("uuid", sa.String(36), unique=True, nullable=False),
        sa.Column("naam", sa.String(100), unique=True, nullable=False),
        sa.Column("code", sa.String(20), unique=True, nullable=False),
        sa.Column("area_label", sa.String(100), nullable=True),
        sa.Column("is_actief", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("verwijderd_op", sa.DateTime(), nullable=True),
        sa.Column("verwijderd_door_id", sa.Integer(), nullable=True),
    )

    # ------------------------------------------------------------------ #
    # Teams                                                                #
    # ------------------------------------------------------------------ #
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("uuid", sa.String(36), unique=True, nullable=False),
        sa.Column("naam", sa.String(100), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("locatie_id", sa.Integer(), sa.ForeignKey("locaties.id"), nullable=False, index=True),
        sa.Column("beschrijving", sa.String(255), nullable=True),
        sa.Column("is_actief", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("verwijderd_op", sa.DateTime(), nullable=True),
        sa.Column("verwijderd_door_id", sa.Integer(), nullable=True),
    )

    op.create_table(
        "team_configs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("standaard_taal", sa.String(5), nullable=False, server_default="nl"),
    )

    # ------------------------------------------------------------------ #
    # Gebruikers                                                           #
    # ------------------------------------------------------------------ #
    op.create_table(
        "gebruikers",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("gebruiker_uuid", sa.String(36), unique=True, nullable=False),
        sa.Column("gebruikersnaam", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("gehashed_wachtwoord", sa.String(), nullable=False),
        sa.Column("volledige_naam", sa.String(150), nullable=False, server_default=""),
        sa.Column("voornaam", sa.String(75), nullable=True),
        sa.Column("achternaam", sa.String(75), nullable=True),
        sa.Column("rol", sa.String(20), nullable=False, server_default="teamlid"),
        sa.Column("locatie_id", sa.Integer(), sa.ForeignKey("locaties.id"), nullable=True, index=True),
        sa.Column("startweek_typedienst", sa.Integer(), nullable=True),
        sa.Column("shift_voorkeuren", sa.String(), nullable=True),
        sa.Column("thema", sa.String(10), nullable=False, server_default="systeem"),
        sa.Column("taal", sa.String(5), nullable=False, server_default="nl"),
        sa.Column("totp_geheim", sa.String(), nullable=True),
        sa.Column("totp_actief", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_actief", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("gedeactiveerd_op", sa.DateTime(), nullable=True),
        sa.Column("laatste_login", sa.DateTime(), nullable=True),
        sa.Column("verwijderd_op", sa.DateTime(), nullable=True),
        sa.Column("verwijderd_door_id", sa.Integer(), nullable=True),
    )

    # ------------------------------------------------------------------ #
    # GebruikerRollen                                                      #
    # ------------------------------------------------------------------ #
    op.create_table(
        "gebruiker_rollen",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("gebruiker_id", sa.Integer(), sa.ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("rol", sa.String(20), nullable=False, index=True),
        sa.Column("scope_id", sa.Integer(), nullable=False, index=True),
        sa.Column("is_reserve", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_actief", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("gebruiker_id", "rol", "scope_id", name="uq_gebruiker_rol_scope"),
    )

    # ------------------------------------------------------------------ #
    # Werkposten & Shiftcodes                                              #
    # ------------------------------------------------------------------ #
    op.create_table(
        "werkposten",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("uuid", sa.String(36), unique=True, nullable=False),
        sa.Column("locatie_id", sa.Integer(), sa.ForeignKey("locaties.id"), nullable=False, index=True),
        sa.Column("naam", sa.String(100), nullable=False),
        sa.Column("beschrijving", sa.Text(), nullable=True),
        sa.Column("telt_als_werkdag", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("reset_12u_rust", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("breekt_werk_reeks", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_actief", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("gedeactiveerd_op", sa.DateTime(), nullable=True),
        sa.Column("verwijderd_op", sa.DateTime(), nullable=True),
        sa.Column("verwijderd_door_id", sa.Integer(), nullable=True),
    )

    op.create_table(
        "shiftcodes",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("uuid", sa.String(36), unique=True, nullable=False),
        sa.Column("werkpost_id", sa.Integer(), sa.ForeignKey("werkposten.id"), nullable=True),
        sa.Column("locatie_id", sa.Integer(), sa.ForeignKey("locaties.id"), nullable=True, index=True),
        sa.Column("dag_type", sa.String(20), nullable=True),
        sa.Column("shift_type", sa.String(20), nullable=True),
        sa.Column("code", sa.String(20), nullable=False, index=True),
        sa.Column("start_uur", sa.String(5), nullable=True),
        sa.Column("eind_uur", sa.String(5), nullable=True),
        sa.Column("is_kritisch", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("telt_als_werkdag", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("is_nachtprestatie", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("reset_nacht", sa.Boolean(), nullable=False, server_default="0"),
    )

    op.create_table(
        "shift_tijden",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("shiftcode", sa.String(10), unique=True, nullable=False, index=True),
        sa.Column("start_tijd", sa.String(8), nullable=True),
        sa.Column("eind_tijd", sa.String(8), nullable=True),
        sa.Column("is_nachtshift", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_rustdag", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("rustdag_type", sa.String(10), nullable=True),
        sa.Column("telt_als_werkdag", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("uren_per_shift", sa.String(5), nullable=True),
    )

    op.create_table(
        "special_codes",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("code", sa.String(20), unique=True, nullable=False),
        sa.Column("naam", sa.String(100), nullable=False),
        sa.Column("term", sa.String(50), nullable=True),
        sa.Column("telt_als_werkdag", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("reset_12u_rust", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("breekt_werk_reeks", sa.Boolean(), nullable=False, server_default="0"),
    )

    # ------------------------------------------------------------------ #
    # Planning                                                             #
    # ------------------------------------------------------------------ #
    op.create_table(
        "planning",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("uuid", sa.String(36), unique=True, nullable=False),
        sa.Column("gebruiker_id", sa.Integer(), sa.ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False, index=True),
        sa.Column("datum", sa.Date(), nullable=False, index=True),
        sa.Column("shift_code", sa.String(20), nullable=True),
        sa.Column("notitie", sa.Text(), nullable=True),
        sa.Column("notitie_gelezen", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="concept"),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("verwijderd_op", sa.DateTime(), nullable=True),
        sa.Column("verwijderd_door_id", sa.Integer(), nullable=True),
        sa.UniqueConstraint("gebruiker_id", "datum", name="uq_planning_gebruiker_datum"),
    )

    op.create_table(
        "planning_overrides",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("planning_shift_id", sa.Integer(), sa.ForeignKey("planning.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("regel_code", sa.String(50), nullable=False, index=True),
        sa.Column("ernst_niveau", sa.String(20), nullable=False),
        sa.Column("overtreding_bericht", sa.Text(), nullable=False),
        sa.Column("reden_afwijking", sa.Text(), nullable=True),
        sa.Column("goedgekeurd_door", sa.Integer(), sa.ForeignKey("gebruikers.id"), nullable=True, index=True),
        sa.Column("goedgekeurd_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "planning_wijzigingen",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("planning_id", sa.Integer(), sa.ForeignKey("planning.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("locatie_id", sa.Integer(), sa.ForeignKey("locaties.id"), nullable=False, index=True),
        sa.Column("gebruiker_id", sa.Integer(), sa.ForeignKey("gebruikers.id"), nullable=True, index=True),
        sa.Column("actie", sa.String(50), nullable=False),
        sa.Column("oude_shift_code", sa.String(20), nullable=True),
        sa.Column("nieuwe_shift_code", sa.String(20), nullable=True),
        sa.Column("tijdstip", sa.DateTime(), server_default=sa.func.now(), nullable=False, index=True),
    )

    op.create_table(
        "rode_lijn_config",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("referentie_datum", sa.Date(), nullable=False),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("gewijzigd_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------ #
    # HR Regels                                                            #
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # Verlof                                                               #
    # ------------------------------------------------------------------ #
    verlof_status_enum = sa.Enum("pending", "goedgekeurd", "geweigerd", name="verlof_status")
    verlof_team_status_enum = sa.Enum("pending", "goedgekeurd", "geweigerd", name="verlof_team_status")

    op.create_table(
        "verlof_aanvragen",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("gebruiker_id", sa.Integer(), sa.ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("start_datum", sa.Date(), nullable=False),
        sa.Column("eind_datum", sa.Date(), nullable=False),
        sa.Column("aantal_dagen", sa.Integer(), nullable=False),
        sa.Column("status", verlof_status_enum, nullable=False, server_default="pending"),
        sa.Column("toegekende_code_term", sa.Text(), nullable=True),
        sa.Column("opmerking", sa.Text(), nullable=True),
        sa.Column("aangevraagd_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("behandeld_door", sa.Integer(), sa.ForeignKey("gebruikers.id"), nullable=True),
        sa.Column("behandeld_op", sa.DateTime(), nullable=True),
        sa.Column("reden_weigering", sa.Text(), nullable=True),
        sa.Column("ingediend_door", sa.Integer(), sa.ForeignKey("gebruikers.id"), nullable=True, index=True),
        sa.Column("verwijderd_op", sa.DateTime(), nullable=True),
        sa.Column("verwijderd_door_id", sa.Integer(), nullable=True),
    )

    op.create_table(
        "verlof_team_statussen",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("verlof_id", sa.Integer(), sa.ForeignKey("verlof_aanvragen.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False, index=True),
        sa.Column("status", verlof_team_status_enum, nullable=False, server_default="pending"),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("behandeld_door_id", sa.Integer(), sa.ForeignKey("gebruikers.id"), nullable=True),
        sa.Column("behandeld_op", sa.DateTime(), nullable=True),
        sa.Column("reden_weigering", sa.Text(), nullable=True),
    )

    saldo_mutatie_type_enum = sa.Enum("jaar_overdracht", "correctie_hr", "vervallen_1mei", name="saldo_mutatie_type")
    saldo_mutatie_veld_enum = sa.Enum("verlof_totaal", "verlof_overgedragen", "kd_totaal", "kd_overgedragen", name="saldo_mutatie_veld")

    op.create_table(
        "verlof_saldi",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("gebruiker_id", sa.Integer(), sa.ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("jaar", sa.Integer(), nullable=False),
        sa.Column("verlof_totaal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verlof_overgedragen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kd_totaal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kd_overgedragen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overdracht_verwerkt_op", sa.DateTime(), nullable=True),
        sa.Column("opmerking", sa.Text(), nullable=True),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("gebruiker_id", "jaar", name="uq_verlof_saldo_gebruiker_jaar"),
    )

    op.create_table(
        "verlof_saldo_mutaties",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("verlof_saldo_id", sa.Integer(), sa.ForeignKey("verlof_saldi.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("mutatie_type", saldo_mutatie_type_enum, nullable=False),
        sa.Column("veld", saldo_mutatie_veld_enum, nullable=False),
        sa.Column("oude_waarde", sa.Integer(), nullable=False),
        sa.Column("nieuwe_waarde", sa.Integer(), nullable=False),
        sa.Column("reden", sa.Text(), nullable=True),
        sa.Column("uitgevoerd_door", sa.Integer(), sa.ForeignKey("gebruikers.id"), nullable=True),
        sa.Column("uitgevoerd_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------ #
    # Notities & Notificaties                                              #
    # ------------------------------------------------------------------ #
    notitie_prioriteit_enum = sa.Enum("laag", "normaal", "hoog", name="notitie_prioriteit")

    op.create_table(
        "notities",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False, index=True),
        sa.Column("van_gebruiker_id", sa.Integer(), sa.ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("naar_gebruiker_id", sa.Integer(), sa.ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("planning_datum", sa.Date(), nullable=True, index=True),
        sa.Column("bericht", sa.Text(), nullable=False),
        sa.Column("is_gelezen", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("prioriteit", notitie_prioriteit_enum, nullable=False, server_default="normaal"),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("gelezen_op", sa.DateTime(), nullable=True),
        sa.Column("verwijderd_op", sa.DateTime(), nullable=True),
        sa.Column("verwijderd_door_id", sa.Integer(), nullable=True),
    )

    op.create_table(
        "notificaties",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("gebruiker_id", sa.Integer(), sa.ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("bericht_sleutel", sa.String(100), nullable=False),
        sa.Column("bericht_params", sa.Text(), nullable=True),
        sa.Column("is_gelezen", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False, index=True),
    )

    # ------------------------------------------------------------------ #
    # Competenties                                                         #
    # ------------------------------------------------------------------ #
    competentie_niveau_enum = sa.Enum("basis", "gevorderd", "expert", name="competentie_niveau")

    op.create_table(
        "competenties",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("locatie_id", sa.Integer(), sa.ForeignKey("locaties.id"), nullable=False, index=True),
        sa.Column("naam", sa.String(150), nullable=False, index=True),
        sa.Column("beschrijving", sa.Text(), nullable=True),
        sa.Column("categorie", sa.String(100), nullable=True),
        sa.Column("is_actief", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("gedeactiveerd_op", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "gebruiker_competenties",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("gebruiker_id", sa.Integer(), sa.ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("competentie_id", sa.Integer(), sa.ForeignKey("competenties.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("niveau", competentie_niveau_enum, nullable=True),
        sa.Column("geldig_tot", sa.Date(), nullable=True),
        sa.Column("aangemaakt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("gebruiker_id", "competentie_id", name="uq_gebruiker_competentie"),
    )

    # ------------------------------------------------------------------ #
    # App Instellingen                                                     #
    # ------------------------------------------------------------------ #
    op.create_table(
        "app_instellingen",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("locatie_id", sa.Integer(), sa.ForeignKey("locaties.id"), nullable=False, index=True),
        sa.Column("sleutel", sa.String(100), nullable=False),
        sa.Column("waarde", sa.String(500), nullable=False, server_default=""),
        sa.Column("bijgewerkt_op", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("bijgewerkt_door", sa.Integer(), sa.ForeignKey("gebruikers.id"), nullable=True),
        sa.UniqueConstraint("locatie_id", "sleutel", name="uq_instelling_locatie_sleutel"),
    )

    # ------------------------------------------------------------------ #
    # Audit Log                                                            #
    # ------------------------------------------------------------------ #
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("tijdstip", sa.DateTime(), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("gebruiker_id", sa.Integer(), sa.ForeignKey("gebruikers.id"), nullable=True, index=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=True, index=True),
        sa.Column("locatie_id", sa.Integer(), sa.ForeignKey("locaties.id"), nullable=True, index=True),
        sa.Column("actie", sa.String(100), nullable=False, index=True),
        sa.Column("doel_type", sa.String(50), nullable=True),
        sa.Column("doel_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("app_instellingen")
    op.drop_table("gebruiker_competenties")
    op.drop_table("competenties")
    op.drop_table("notificaties")
    op.drop_table("notities")
    op.drop_table("verlof_saldo_mutaties")
    op.drop_table("verlof_saldi")
    op.drop_table("verlof_team_statussen")
    op.drop_table("verlof_aanvragen")
    op.drop_table("hr_regels")
    op.drop_table("rode_lijn_config")
    op.drop_table("planning_wijzigingen")
    op.drop_table("planning_overrides")
    op.drop_table("planning")
    op.drop_table("special_codes")
    op.drop_table("shift_tijden")
    op.drop_table("shiftcodes")
    op.drop_table("werkposten")
    op.drop_table("gebruiker_rollen")
    op.drop_table("gebruikers")
    op.drop_table("team_configs")
    op.drop_table("teams")
    op.drop_table("locaties")

    # Drop custom enum types (PostgreSQL)
    for enum_name in (
        "verlof_status", "verlof_team_status",
        "saldo_mutatie_type", "saldo_mutatie_veld",
        "notitie_prioriteit", "competentie_niveau",
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
