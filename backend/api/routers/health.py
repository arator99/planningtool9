from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.dependencies import haal_db
from config import instellingen

router = APIRouter(prefix="/health", tags=["gezondheid"])


@router.get("")
def gezondheidscheck(db: Session = Depends(haal_db)) -> dict:
    """Controleert of de app en database bereikbaar zijn. Gebruikt door Docker healthcheck."""
    try:
        db.execute(text("SELECT 1"))
        if instellingen.omgeving == "development":
            return {"status": "ok", "versie": instellingen.app_versie, "omgeving": instellingen.omgeving}
        return {"status": "ok"}
    except Exception as fout:
        raise HTTPException(status_code=503, detail="Database niet bereikbaar") from fout
