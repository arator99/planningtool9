from sqlalchemy import Column, DateTime, Enum as SAEnum, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from database import Basis

MUTATIE_TYPES = ("jaar_overdracht", "correctie_hr", "vervallen_1mei")
MUTATIE_VELDEN = ("verlof_totaal", "verlof_overgedragen", "kd_totaal", "kd_overgedragen")


class VerlofSaldo(Basis):
    """Verlof saldo per gebruiker per jaar."""

    __tablename__ = "verlof_saldi"
    __table_args__ = (UniqueConstraint("gebruiker_id", "jaar", name="uq_verlof_saldo_gebruiker_jaar"),)

    id = Column(Integer, primary_key=True, index=True)
    gebruiker_id = Column(Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True)
    groep_id = Column(Integer, ForeignKey("groepen.id"), nullable=False, index=True)
    jaar = Column(Integer, nullable=False)

    # VV (verlofverlof)
    verlof_totaal = Column(Integer, default=0, nullable=False)
    verlof_overgedragen = Column(Integer, default=0, nullable=False)

    # KD (kompensatiedag)
    kd_totaal = Column(Integer, default=0, nullable=False)
    kd_overgedragen = Column(Integer, default=0, nullable=False)

    # Meta
    overdracht_verwerkt_op = Column(DateTime, nullable=True)
    opmerking = Column(Text, nullable=True)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Relaties
    gebruiker = relationship("Gebruiker", foreign_keys=[gebruiker_id])
    mutaties = relationship("VerlofSaldoMutatie", back_populates="saldo", cascade="all, delete-orphan",
                            order_by="VerlofSaldoMutatie.uitgevoerd_op.desc()")


class VerlofSaldoMutatie(Basis):
    """Audit trail voor saldo wijzigingen."""

    __tablename__ = "verlof_saldo_mutaties"

    id = Column(Integer, primary_key=True, index=True)
    verlof_saldo_id = Column(Integer, ForeignKey("verlof_saldi.id", ondelete="CASCADE"), nullable=False, index=True)

    mutatie_type = Column(SAEnum(*MUTATIE_TYPES, name="saldo_mutatie_type"), nullable=False)
    veld = Column(SAEnum(*MUTATIE_VELDEN, name="saldo_mutatie_veld"), nullable=False)
    oude_waarde = Column(Integer, nullable=False)
    nieuwe_waarde = Column(Integer, nullable=False)
    reden = Column(Text, nullable=True)

    uitgevoerd_door = Column(Integer, ForeignKey("gebruikers.id"), nullable=True)
    uitgevoerd_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Relaties
    saldo = relationship("VerlofSaldo", back_populates="mutaties")
    uitvoerder = relationship("Gebruiker", foreign_keys=[uitgevoerd_door])
