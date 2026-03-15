"""Verlof saldo domein — pure business logic, geen database afhankelijkheden."""
from dataclasses import dataclass
from datetime import date

# Business rule constanten
MAX_KD_OVERDRACHT = 35      # Max KD dagen overdragen naar volgend jaar
VV_VERVAL_MAAND = 5         # Overgedragen VV vervalt op 1 mei
VV_VERVAL_DAG = 1

TOEGESTANE_VELDEN = ("verlof_totaal", "verlof_overgedragen", "kd_totaal", "kd_overgedragen")
KD_TERMS = {"kd", "kompensatiedag"}  # lowercase voor vergelijking


def is_kd_term(term: str | None) -> bool:
    """Check of een verlofcode term een KD-type is."""
    if not term:
        return False
    return term.lower() in KD_TERMS


@dataclass
class VerlofFifoVerdeling:
    """FIFO-verdeling van verlof over vorig jaar pot en huidig jaar pot."""

    vorig_jaar_recht: int
    vorig_jaar_aangevraagd: int
    vorig_jaar_opgenomen: int
    vorig_jaar_beschikbaar: int

    huidig_jaar_recht: int
    huidig_jaar_aangevraagd: int
    huidig_jaar_opgenomen: int
    huidig_jaar_beschikbaar: int

    @property
    def totaal_recht(self) -> int:
        return self.vorig_jaar_recht + self.huidig_jaar_recht

    @property
    def totaal_aangevraagd(self) -> int:
        return self.vorig_jaar_aangevraagd + self.huidig_jaar_aangevraagd

    @property
    def totaal_opgenomen(self) -> int:
        return self.vorig_jaar_opgenomen + self.huidig_jaar_opgenomen

    @property
    def totaal_beschikbaar(self) -> int:
        return self.vorig_jaar_beschikbaar + self.huidig_jaar_beschikbaar


def bereken_fifo(
    vorig_jaar_recht: int,
    huidig_jaar_recht: int,
    totaal_opgenomen: int,
    totaal_aangevraagd: int,
) -> VerlofFifoVerdeling:
    """
    Bereken FIFO-verdeling over vorig jaar pot en huidig jaar pot.

    FIFO: opgenomen/aangevraagde dagen worden eerst uit de overgedragen pot gehaald.
    """
    # Opgenomen: eerst uit vorig jaar pot
    vorig_jaar_opgenomen = min(vorig_jaar_recht, totaal_opgenomen)
    huidig_jaar_opgenomen = max(0, totaal_opgenomen - vorig_jaar_recht)

    # Aangevraagd: eerst uit restant vorig jaar pot (na opgenomen)
    vorig_jaar_restant = vorig_jaar_recht - vorig_jaar_opgenomen
    vorig_jaar_aangevraagd = min(vorig_jaar_restant, totaal_aangevraagd)
    huidig_jaar_aangevraagd = max(0, totaal_aangevraagd - vorig_jaar_restant)

    return VerlofFifoVerdeling(
        vorig_jaar_recht=vorig_jaar_recht,
        vorig_jaar_aangevraagd=vorig_jaar_aangevraagd,
        vorig_jaar_opgenomen=vorig_jaar_opgenomen,
        vorig_jaar_beschikbaar=max(0, vorig_jaar_recht - vorig_jaar_aangevraagd - vorig_jaar_opgenomen),
        huidig_jaar_recht=huidig_jaar_recht,
        huidig_jaar_aangevraagd=huidig_jaar_aangevraagd,
        huidig_jaar_opgenomen=huidig_jaar_opgenomen,
        huidig_jaar_beschikbaar=max(0, huidig_jaar_recht - huidig_jaar_aangevraagd - huidig_jaar_opgenomen),
    )


def bereken_kd_overdracht(kd_restant: int) -> tuple[int, int]:
    """
    Bereken KD overdracht naar volgend jaar.

    Returns:
        (overdracht, vervallen) — max MAX_KD_OVERDRACHT, rest vervalt
    """
    overdracht = min(max(0, kd_restant), MAX_KD_OVERDRACHT)
    vervallen = max(0, kd_restant - MAX_KD_OVERDRACHT)
    return overdracht, vervallen


def check_1_mei_waarschuwing(
    vorig_jaar_beschikbaar: int,
    vorig_jaar_recht: int,
    vandaag: date,
) -> str | None:
    """
    Geef waarschuwingstekst als er nog overgedragen VV dagen zijn voor 1 mei.
    Enkel actief van januari t/m april.
    """
    if vandaag.month >= VV_VERVAL_MAAND:
        return None
    if vorig_jaar_recht <= 0 or vorig_jaar_beschikbaar <= 0:
        return None

    verval_datum = date(vandaag.year, VV_VERVAL_MAAND, VV_VERVAL_DAG)
    dagen_tot_verval = (verval_datum - vandaag).days
    return (
        f"Let op: Je hebt nog {vorig_jaar_beschikbaar} overgedragen verlofdagen "
        f"die voor 1 mei moeten worden opgenomen! ({dagen_tot_verval} dagen resterend)"
    )


def valideer_saldo_aanpassing(veld: str, nieuwe_waarde: int, reden: str) -> None:
    """
    Valideer parameters voor handmatige saldo aanpassing.

    Raises:
        ValueError: bij ongeldige input
    """
    if veld not in TOEGESTANE_VELDEN:
        raise ValueError(f"Ongeldig veld. Kies uit: {', '.join(TOEGESTANE_VELDEN)}")
    if nieuwe_waarde < 0:
        raise ValueError("Nieuwe waarde mag niet negatief zijn.")
    if not reden or len(reden.strip()) < 10:
        raise ValueError("Reden is verplicht en moet minimaal 10 karakters bevatten.")
