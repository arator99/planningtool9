"""BaseRepository — gemeenschappelijke basis voor alle repository-klassen.

Zorgt voor automatische tenant-isolatie via _locatie_filter() en soft-delete
filtering via _basis_filter(). Alle repositories erven van deze klasse.

Gebruik:
    class TeamRepository(BaseRepository):
        def haal_alle(self) -> list[Team]:
            return self._basis_filter(self.db.query(Team), Team).all()

locatie_id=None reserveert voor super_beheerder (geen locatie-filter).
"""
from sqlalchemy.orm import Session


class BaseRepository:
    """Basisklasse voor alle repositories met tenant-isolatie en soft-delete.

    Args:
        db: SQLAlchemy sessie.
        locatie_id: Locatie-ID voor tenant-filter. None = super_beheerder (geen filter).
    """

    def __init__(self, db: Session, locatie_id: int | None) -> None:
        self.db = db
        self.locatie_id = locatie_id

    def _locatie_filter(self, query, model):
        """Pas locatie-filter toe op een query.

        Geen filter als locatie_id is None (super_beheerder heeft toegang tot alles).
        """
        if self.locatie_id is not None:
            query = query.filter(model.locatie_id == self.locatie_id)
        return query

    def _basis_filter(self, query, model):
        """Voeg standaard soft-delete + locatie-filter toe.

        Filtert op is_actief=True, verwijderd_op IS NULL (indien aanwezig),
        en locatie_id (indien locatie_id is ingesteld).
        """
        query = query.filter(model.is_actief == True)  # noqa: E712
        if hasattr(model, "verwijderd_op"):
            query = query.filter(model.verwijderd_op.is_(None))
        return self._locatie_filter(query, model)
