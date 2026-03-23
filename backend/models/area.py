"""Area model — groepeert locaties voor HR-scoping op area-niveau."""
import uuid as uuid_module

from sqlalchemy import Boolean, Column, DateTime, Integer, String, func

from database import Basis


class Area(Basis):
    """
    Area — groepeert meerdere locaties voor HR-overzicht.

    HR-gebruikers worden gescoopt op area_id zodat ze alle locaties
    binnen hun area kunnen inzien zonder super_beheerder te zijn.
    """

    __tablename__ = "areas"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(
        String(36), unique=True, nullable=False,
        default=lambda: str(uuid_module.uuid4()),
    )
    naam = Column(String(100), unique=True, nullable=False)
    code = Column(String(20), unique=True, nullable=False)  # bijv. "AREA_WEST"
    is_actief = Column(Boolean, default=True, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Soft delete
    verwijderd_op = Column(DateTime, nullable=True)
    verwijderd_door_id = Column(Integer, nullable=True)
