from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from database import Basis


class Notificatie(Basis):
    """In-app notificatie voor een gebruiker (geen e-mail)."""

    __tablename__ = "notificaties"

    id = Column(Integer, primary_key=True, index=True)
    gebruiker_id = Column(Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True)
    bericht_sleutel = Column(String(100), nullable=False)   # i18n sleutel, bijv. "verlof.request.approved"
    bericht_params = Column(Text, nullable=True)             # JSON string met parameters
    is_gelezen = Column(Boolean, default=False, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    # Relatie
    gebruiker = relationship("Gebruiker", back_populates="notificaties")
