"""Verlof saldo service — saldo beheer, FIFO berekening, jaar overdracht."""
import logging
from datetime import date, datetime

from sqlalchemy import extract
from sqlalchemy.orm import Session

from models.gebruiker import Gebruiker
from models.lidmaatschap import Lidmaatschap
from models.team import Team
from models.verlof import VerlofAanvraag
from models.verlof_saldo import VerlofSaldo, VerlofSaldoMutatie
from services.domein.verlof_saldo_domein import (
    VerlofFifoVerdeling,
    bereken_fifo,
    bereken_kd_overdracht,
    check_1_mei_waarschuwing,
    is_kd_term,
    valideer_saldo_aanpassing,
)

logger = logging.getLogger(__name__)


class VerlofSaldoService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Ophalen                                                              #
    # ------------------------------------------------------------------ #

    def haal_saldo(self, gebruiker_id: int, jaar: int) -> VerlofSaldo | None:
        return (
            self.db.query(VerlofSaldo)
            .filter(VerlofSaldo.gebruiker_id == gebruiker_id, VerlofSaldo.jaar == jaar)
            .first()
        )

    def haal_of_maak_saldo(self, gebruiker_id: int, jaar: int) -> VerlofSaldo:
        """Haal saldo op of maak nieuw aan als het niet bestaat."""
        saldo = self.haal_saldo(gebruiker_id, jaar)
        if not saldo:
            saldo = VerlofSaldo(
                gebruiker_id=gebruiker_id,
                jaar=jaar,
            )
            self.db.add(saldo)
            self.db.commit()
            self.db.refresh(saldo)
        return saldo

    def haal_alle_saldi(self, locatie_id: int, jaar: int) -> list[dict]:
        """
        Alle saldi voor een locatie in een jaar, inclusief berekende restanten.
        Medewerkers zonder saldo record krijgen nullen.
        """
        medewerkers = (
            self.db.query(Gebruiker)
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .join(Team, Team.id == Lidmaatschap.team_id)
            .filter(
                Team.locatie_id == locatie_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
                Gebruiker.is_actief == True,
            )
            .distinct()
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

        resultaat = []
        for m in medewerkers:
            saldo = self.haal_saldo(m.id, jaar)
            stats = self._bereken_stats(m.id, jaar)
            overzicht = self._bouw_overzicht(m, saldo, stats, jaar)
            resultaat.append(overzicht)
        return resultaat

    def bereken_overzicht(self, gebruiker_id: int, jaar: int) -> dict:
        """
        Volledig saldo overzicht voor één gebruiker:
        saldo, FIFO verdeling VV + KD, en eventuele 1-mei-waarschuwing.
        """
        gebruiker = self.db.query(Gebruiker).filter(Gebruiker.id == gebruiker_id).first()
        saldo = self.haal_saldo(gebruiker_id, jaar)
        stats = self._bereken_stats(gebruiker_id, jaar)
        return self._bouw_overzicht(gebruiker, saldo, stats, jaar)

    # ------------------------------------------------------------------ #
    # Aanpassen                                                            #
    # ------------------------------------------------------------------ #

    def pas_saldo_aan(
        self,
        gebruiker_id: int,
        jaar: int,
        veld: str,
        nieuwe_waarde: int,
        reden: str,
        uitgevoerd_door_id: int,
    ) -> VerlofSaldo:
        """
        Pas een saldo veld handmatig aan met volledige audit trail.

        Raises:
            ValueError: bij ongeldige input
        """
        valideer_saldo_aanpassing(veld, nieuwe_waarde, reden)

        saldo = self.haal_of_maak_saldo(gebruiker_id, jaar)
        oude_waarde = getattr(saldo, veld)

        if oude_waarde == nieuwe_waarde:
            return saldo

        setattr(saldo, veld, nieuwe_waarde)

        mutatie = VerlofSaldoMutatie(
            verlof_saldo_id=saldo.id,
            mutatie_type="correctie_hr",
            veld=veld,
            oude_waarde=oude_waarde,
            nieuwe_waarde=nieuwe_waarde,
            reden=reden.strip(),
            uitgevoerd_door=uitgevoerd_door_id,
        )
        self.db.add(mutatie)
        self.db.commit()
        self.db.refresh(saldo)

        logger.info(
            "Saldo aangepast: gebruiker %s jaar %s: %s %s→%s (%s)",
            gebruiker_id, jaar, veld, oude_waarde, nieuwe_waarde, reden,
        )
        return saldo

    # ------------------------------------------------------------------ #
    # Jaar overdracht                                                      #
    # ------------------------------------------------------------------ #

    def voer_jaar_overdracht_uit(
        self,
        locatie_id: int,
        van_jaar: int,
        naar_jaar: int,
        uitgevoerd_door_id: int,
    ) -> dict:
        """
        Voer jaar overdracht uit voor alle medewerkers van de locatie.

        Business rules:
        - VV: alle resterende dagen worden overgedragen
        - KD: max MAX_KD_OVERDRACHT dagen, rest vervalt
        - Negatief saldo: wordt afgetrokken van volgend jaar totaal

        Returns:
            Dict met statistieken van de overdracht
        """
        medewerkers = (
            self.db.query(Gebruiker)
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .join(Team, Team.id == Lidmaatschap.team_id)
            .filter(
                Team.locatie_id == locatie_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
                Gebruiker.is_actief == True,
            )
            .distinct()
            .all()
        )

        stats = {
            "aantal_gebruikers": 0,
            "totaal_vv_overgedragen": 0,
            "totaal_kd_overgedragen": 0,
            "totaal_kd_vervallen": 0,
            "aantal_negatief": 0,
            "fouten": [],
        }

        for m in medewerkers:
            try:
                vv_over, kd_over, kd_verf, heeft_negatief = self._verwerk_overdracht(
                    m.id, van_jaar, naar_jaar, uitgevoerd_door_id
                )
                stats["aantal_gebruikers"] += 1
                stats["totaal_vv_overgedragen"] += vv_over
                stats["totaal_kd_overgedragen"] += kd_over
                stats["totaal_kd_vervallen"] += kd_verf
                if heeft_negatief:
                    stats["aantal_negatief"] += 1
            except Exception as e:
                fout = f"{m.volledige_naam or m.gebruikersnaam}: {e}"
                stats["fouten"].append(fout)
                logger.error("Fout bij overdracht voor gebruiker %s: %s", m.id, e, exc_info=True)

        logger.info(
            "Jaar overdracht %s→%s: %s gebruikers, VV %s, KD %s (vervallen %s)",
            van_jaar, naar_jaar,
            stats["aantal_gebruikers"],
            stats["totaal_vv_overgedragen"],
            stats["totaal_kd_overgedragen"],
            stats["totaal_kd_vervallen"],
        )
        return stats

    # ------------------------------------------------------------------ #
    # 1 mei verval                                                         #
    # ------------------------------------------------------------------ #

    def verwerk_1_mei_verval(self, locatie_id: int, jaar: int, uitgevoerd_door_id: int) -> int:
        """
        Zet verlof_overgedragen op 0 voor alle medewerkers van de locatie (na 1 mei).

        Returns:
            Aantal medewerkers met vervallen dagen
        """
        # Haal gebruiker_ids op voor de locatie via lidmaatschappen
        gebruiker_ids = [
            g.id for g in self.db.query(Gebruiker)
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .join(Team, Team.id == Lidmaatschap.team_id)
            .filter(
                Team.locatie_id == locatie_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
                Gebruiker.is_actief == True,
            )
            .distinct()
            .all()
        ]
        saldi = (
            self.db.query(VerlofSaldo)
            .filter(
                VerlofSaldo.gebruiker_id.in_(gebruiker_ids),
                VerlofSaldo.jaar == jaar,
                VerlofSaldo.verlof_overgedragen > 0,
            )
            .all()
        )

        aantal = 0
        for saldo in saldi:
            oude_waarde = saldo.verlof_overgedragen
            saldo.verlof_overgedragen = 0
            mutatie = VerlofSaldoMutatie(
                verlof_saldo_id=saldo.id,
                mutatie_type="vervallen_1mei",
                veld="verlof_overgedragen",
                oude_waarde=oude_waarde,
                nieuwe_waarde=0,
                reden=f"Overgedragen verlofdagen vervallen na 1 mei {jaar}",
                uitgevoerd_door=uitgevoerd_door_id,
            )
            self.db.add(mutatie)
            aantal += 1

        self.db.commit()
        logger.info("1-mei verval %s: %s medewerkers", jaar, aantal)
        return aantal

    # ------------------------------------------------------------------ #
    # Intern                                                               #
    # ------------------------------------------------------------------ #

    def _bereken_stats(self, gebruiker_id: int, jaar: int) -> dict:
        """Bereken opgenomen en aangevraagde VV/KD dagen uit VerlofAanvraag."""
        aanvragen = (
            self.db.query(VerlofAanvraag)
            .filter(
                VerlofAanvraag.gebruiker_id == gebruiker_id,
                extract("year", VerlofAanvraag.start_datum) == jaar,
                VerlofAanvraag.status.in_(["goedgekeurd", "pending"]),
            )
            .all()
        )

        stats = {
            "vv_opgenomen": 0, "vv_aangevraagd": 0,
            "kd_opgenomen": 0, "kd_aangevraagd": 0,
        }

        for a in aanvragen:
            if a.status == "goedgekeurd":
                if is_kd_term(a.toegekende_code_term):
                    stats["kd_opgenomen"] += a.aantal_dagen
                else:
                    stats["vv_opgenomen"] += a.aantal_dagen
            elif a.status == "pending":
                stats["vv_aangevraagd"] += a.aantal_dagen

        return stats

    def _bouw_overzicht(
        self,
        gebruiker: Gebruiker,
        saldo: VerlofSaldo | None,
        stats: dict,
        jaar: int,
    ) -> dict:
        """Bouw volledig overzicht dict met FIFO verdeling en waarschuwing."""
        verlof_totaal = saldo.verlof_totaal if saldo else 0
        verlof_over = saldo.verlof_overgedragen if saldo else 0
        kd_totaal = saldo.kd_totaal if saldo else 0
        kd_over = saldo.kd_overgedragen if saldo else 0

        vv_fifo = bereken_fifo(verlof_over, verlof_totaal, stats["vv_opgenomen"], stats["vv_aangevraagd"])
        kd_fifo = bereken_fifo(kd_over, kd_totaal, stats["kd_opgenomen"], stats["kd_aangevraagd"])

        waarschuwing = check_1_mei_waarschuwing(
            vv_fifo.vorig_jaar_beschikbaar,
            vv_fifo.vorig_jaar_recht,
            date.today(),
        )

        return {
            "gebruiker_id": gebruiker.id if gebruiker else None,
            "naam": (gebruiker.volledige_naam or gebruiker.gebruikersnaam) if gebruiker else "",
            "saldo_id": saldo.id if saldo else None,
            "jaar": jaar,
            # VV
            "verlof_totaal": verlof_totaal,
            "verlof_overgedragen": verlof_over,
            "vv_opgenomen": stats["vv_opgenomen"],
            "vv_aangevraagd": stats["vv_aangevraagd"],
            "vv_restant": vv_fifo.totaal_beschikbaar,
            "vv_fifo": vv_fifo,
            # KD
            "kd_totaal": kd_totaal,
            "kd_overgedragen": kd_over,
            "kd_opgenomen": stats["kd_opgenomen"],
            "kd_aangevraagd": stats["kd_aangevraagd"],
            "kd_restant": kd_fifo.totaal_beschikbaar,
            "kd_fifo": kd_fifo,
            # Meta
            "waarschuwing": waarschuwing,
            "overdracht_verwerkt_op": saldo.overdracht_verwerkt_op if saldo else None,
        }

    def _verwerk_overdracht(
        self,
        gebruiker_id: int,
        van_jaar: int,
        naar_jaar: int,
        uitgevoerd_door_id: int,
    ) -> tuple[int, int, int, bool]:
        """
        Verwerk jaar overdracht voor één gebruiker.

        Returns:
            (vv_overgedragen, kd_overgedragen, kd_vervallen, heeft_negatief)
        """
        stats = self._bereken_stats(gebruiker_id, van_jaar)
        van_saldo = self.haal_saldo(gebruiker_id, van_jaar)

        verlof_totaal = van_saldo.verlof_totaal if van_saldo else 0
        verlof_over = van_saldo.verlof_overgedragen if van_saldo else 0
        kd_totaal = van_saldo.kd_totaal if van_saldo else 0
        kd_over = van_saldo.kd_overgedragen if van_saldo else 0

        vv_restant = (verlof_totaal + verlof_over) - stats["vv_opgenomen"] - stats["vv_aangevraagd"]
        kd_restant = (kd_totaal + kd_over) - stats["kd_opgenomen"] - stats["kd_aangevraagd"]

        heeft_negatief = vv_restant < 0 or kd_restant < 0

        vv_overdracht = max(0, vv_restant)
        vv_aftrek = abs(min(0, vv_restant))

        kd_overdracht, kd_vervallen = bereken_kd_overdracht(kd_restant)
        kd_aftrek = abs(min(0, kd_restant))

        # Haal of maak saldo voor naar_jaar
        naar_saldo = self.haal_of_maak_saldo(gebruiker_id, naar_jaar)

        def _update(veld: str, nieuwe_waarde: int, reden: str) -> None:
            oude = getattr(naar_saldo, veld)
            if oude == nieuwe_waarde:
                return
            setattr(naar_saldo, veld, nieuwe_waarde)
            self.db.add(VerlofSaldoMutatie(
                verlof_saldo_id=naar_saldo.id,
                mutatie_type="jaar_overdracht",
                veld=veld,
                oude_waarde=oude,
                nieuwe_waarde=nieuwe_waarde,
                reden=reden,
                uitgevoerd_door=uitgevoerd_door_id,
            ))

        _update("verlof_overgedragen", vv_overdracht,
                f"Jaar overdracht {van_jaar}→{naar_jaar}")

        _update("kd_overgedragen", kd_overdracht,
                f"Jaar overdracht {van_jaar}→{naar_jaar}"
                + (f" (max 35, {kd_vervallen} vervallen)" if kd_vervallen > 0 else ""))

        if vv_aftrek > 0:
            _update("verlof_totaal", max(0, naar_saldo.verlof_totaal - vv_aftrek),
                    f"Negatief VV saldo {van_jaar} ({vv_aftrek} dagen) afgetrokken")

        if kd_aftrek > 0:
            _update("kd_totaal", max(0, naar_saldo.kd_totaal - kd_aftrek),
                    f"Negatief KD saldo {van_jaar} ({kd_aftrek} dagen) afgetrokken")

        naar_saldo.overdracht_verwerkt_op = datetime.now()
        self.db.commit()

        return vv_overdracht, kd_overdracht, kd_vervallen, heeft_negatief
