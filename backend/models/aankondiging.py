"""Aankondiging model — onderhoudsmeldingen en systeemberichten voor alle gebruikers."""
import uuid as uuid_module

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func

from database import Basis

# Toegestane sjablonen — sleutel stemt overeen met i18n-prefix aankondiging.sjabloon.<sleutel>.*
AANKONDIGING_SJABLONEN = (
    "onderhoud_gepland",
    "update_gepland",
    "stroomonderbreking",
    "server_herstart",
    "storing",
    "overige",
)


class Aankondiging(Basis):
    """Systeemaankondiging zichtbaar voor alle ingelogde gebruikers."""

    __tablename__ = "aankondigingen"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_module.uuid4()))
    sjabloon = Column(String(50), nullable=False, default="onderhoud_gepland")  # zie AANKONDIGING_SJABLONEN
    extra_info = Column(Text, nullable=True)   # optionele vrije tekst (niet vertaald)
    ernst = Column(String(20), nullable=False, default="info")   # info | waarschuwing | kritiek
    type = Column(String(20), nullable=False, default="banner")  # banner | dialoog
    gepland_van = Column(DateTime, nullable=True)
    gepland_tot = Column(DateTime, nullable=True)
    is_actief = Column(Boolean, default=False, nullable=False)
    aangemaakt_door_id = Column(Integer, ForeignKey("gebruikers.id"), nullable=True)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
