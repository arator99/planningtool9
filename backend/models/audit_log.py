from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from database import Basis


class AuditLog(Basis):
    """Audit trail — wie heeft wat gewijzigd en wanneer."""

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    tijdstip = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    gebruiker_id = Column(Integer, ForeignKey("gebruikers.id"), nullable=True, index=True)
    groep_id = Column(Integer, ForeignKey("groepen.id"), nullable=True, index=True)
    actie = Column(String(100), nullable=False, index=True)   # bijv. "shift.aanmaken", "verlof.goedkeuren"
    doel_type = Column(String(50), nullable=True)              # bijv. "Planning", "VerlofAanvraag"
    doel_id = Column(Integer, nullable=True)
    detail = Column(Text, nullable=True)                       # JSON string met voor/na waarden

    # Relatie
    gebruiker = relationship("Gebruiker", back_populates="audit_acties", foreign_keys=[gebruiker_id])
