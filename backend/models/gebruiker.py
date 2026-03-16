"""Gebruiker model — authenticatie, autorisatie en profiel."""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from database import Basis

# Alle geldige rollen — ook gebruikt als denormalized display veld
ROLLEN = ("teamlid", "planner", "hr", "beheerder", "super_beheerder")


class Gebruiker(Basis):
    """Gebruiker — authenticatie, autorisatie en profiel."""

    __tablename__ = "gebruikers"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    gebruikersnaam = Column(String(50), unique=True, nullable=False, index=True)
    gehashed_wachtwoord = Column(String, nullable=False)

    # Profiel
    volledige_naam = Column(String(150), nullable=False, default="")
    voornaam = Column(String(75), nullable=True)
    achternaam = Column(String(75), nullable=True)

    # Autorisatie
    # `rol` is een gedenormaliseerde weergave van de hoogste GebruikerRol —
    # enkel voor display en snelle queries. Authorisatie altijd via GebruikerRol.
    rol = Column(String(20), nullable=False, default="teamlid")

    # Locatie FK — de primaire locatie van de gebruiker (tenant-isolatie)
    locatie_id = Column(Integer, ForeignKey("locaties.id"), nullable=True, index=True)

    # Planningsinstellingen
    startweek_typedienst = Column(Integer, nullable=True)  # 1-6
    shift_voorkeuren = Column(String, nullable=True)       # JSON string

    # Voorkeursinstellingen
    thema = Column(String(10), default="systeem", nullable=False)  # light | dark | systeem
    taal = Column(String(5), default="nl", nullable=False)

    # 2FA
    totp_geheim = Column(String, nullable=True)
    totp_actief = Column(Boolean, default=False, nullable=False)

    # Status & tijdstempels
    is_actief = Column(Boolean, default=True, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    gedeactiveerd_op = Column(DateTime, nullable=True)
    laatste_login = Column(DateTime, nullable=True)

    # Soft delete
    verwijderd_op = Column(DateTime, nullable=True)
    verwijderd_door_id = Column(Integer, nullable=True)

    # Relaties
    locatie = relationship("Locatie")
    rollen = relationship("GebruikerRol", back_populates="gebruiker", cascade="all, delete-orphan")
    planning_shifts = relationship("Planning", back_populates="gebruiker", cascade="all, delete-orphan")
    verlof_aanvragen = relationship(
        "VerlofAanvraag",
        back_populates="gebruiker",
        foreign_keys="VerlofAanvraag.gebruiker_id",
        cascade="all, delete-orphan",
    )
    competenties = relationship("GebruikerCompetentie", back_populates="gebruiker", cascade="all, delete-orphan")
    verzonden_notities = relationship(
        "Notitie", back_populates="van_gebruiker", foreign_keys="Notitie.van_gebruiker_id"
    )
    ontvangen_notities = relationship(
        "Notitie", back_populates="naar_gebruiker", foreign_keys="Notitie.naar_gebruiker_id"
    )
    notificaties = relationship("Notificatie", back_populates="gebruiker", cascade="all, delete-orphan")
    audit_acties = relationship(
        "AuditLog", back_populates="gebruiker", foreign_keys="AuditLog.gebruiker_id"
    )
