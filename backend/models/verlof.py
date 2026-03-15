from sqlalchemy import Column, Date, DateTime, Enum as SAEnum, ForeignKey, Integer, Text, func
from sqlalchemy.orm import relationship

from database import Basis

VERLOF_STATUSSEN = ("pending", "goedgekeurd", "geweigerd")


class VerlofAanvraag(Basis):
    """Verlofaanvraag van een medewerker."""

    __tablename__ = "verlof_aanvragen"

    id = Column(Integer, primary_key=True, index=True)
    gebruiker_id = Column(Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True)
    groep_id = Column(Integer, ForeignKey("groepen.id"), nullable=False, index=True)

    # Periode
    start_datum = Column(Date, nullable=False)
    eind_datum = Column(Date, nullable=False)
    aantal_dagen = Column(Integer, nullable=False)

    # Status
    status = Column(SAEnum(*VERLOF_STATUSSEN, name="verlof_status"), default="pending", nullable=False)
    toegekende_code_term = Column(Text, nullable=True)   # VV, KD, VP
    opmerking = Column(Text, nullable=True)

    # Tijdstempels
    aangevraagd_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Behandeling
    behandeld_door = Column(Integer, ForeignKey("gebruikers.id"), nullable=True)
    behandeld_op = Column(DateTime, nullable=True)
    reden_weigering = Column(Text, nullable=True)

    # Namens-aanvraag (v0.7.50)
    ingediend_door = Column(Integer, ForeignKey("gebruikers.id"), nullable=True, index=True)

    # Relaties
    gebruiker = relationship("Gebruiker", back_populates="verlof_aanvragen", foreign_keys=[gebruiker_id])
    behandelaar = relationship("Gebruiker", foreign_keys=[behandeld_door])
    indiener = relationship("Gebruiker", foreign_keys=[ingediend_door])
