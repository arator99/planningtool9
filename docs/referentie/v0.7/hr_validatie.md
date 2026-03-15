# HR Validatie Referentie

**Versie:** 0.7.x
**Laatst bijgewerkt:** 2026-03-01
**Doel:** Complete referentie van het HR validatie systeem, validators en ValidatieContext

---

## Inhoudsopgave

1. [Overzicht](#overzicht)
2. [Architectuur](#architectuur)
3. [Validators](#validators)
4. [ValidatieContext](#validatiecontext)
5. [HRConfig](#hrconfig)
6. [Service API](#service-api)
7. [Domein Objecten](#domein-objecten)
8. [Gebruik in Code](#gebruik-in-code)

---

## Overzicht

Het HR validatie systeem controleert planningen tegen arbeidstijdregels. Het gebruikt een **Strategy Pattern** met 10 onafhankelijke validators die elk één regel controleren.

### Kenmerken

- **Maand-gebaseerd**: Validatie per maand met context van vorige periode
- **Gecached**: Resultaten worden gecached per (jaar, maand)
- **Thread-safe**: Class-level locks voor cache operaties
- **Incrementeel**: Ondersteunt enkele-shift validatie voor realtime feedback

---

## Architectuur

```
┌─────────────────────────────────────────────────────────────────┐
│                     HRValidatieService                          │
│                   (Orchestrator - Applicatie laag)              │
├─────────────────────────────────────────────────────────────────┤
│  haal_hr_config()           → HRConfig                          │
│  valideer_maandplanning()   → ValidatieRapport                  │
│  valideer_enkele_shift()    → List[RegelOvertreding]            │
│  valideer_met_shifts()      → ValidatieRapport (in-memory)      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AbstractRegelValidator                        │
│                     (Strategy Pattern - Domein laag)             │
├─────────────────────────────────────────────────────────────────┤
│  valideer(shifts, config) → List[RegelOvertreding]              │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Validator 1   │   │ Validator 2   │   │ Validator N   │
│ (KritiekeShift)│   │ (DubbeleShift)│   │    (...)      │
└───────────────┘   └───────────────┘   └───────────────┘
```

### Bestanden

| Locatie | Doel |
|---------|------|
| `src/services/applicatie/hr_validatie_service.py` | Orchestratie, caching |
| `src/services/domein/hr_regel_domein.py` | Dataclasses, AbstractRegelValidator |
| `src/services/domein/validators/` | Individuele validators |
| `src/services/repo/hr_regel_repo.py` | Database queries |

---

## Validators

### Overzicht

| Validator | Regel Code | Ernst | Beschrijving |
|-----------|------------|-------|--------------|
| KritiekeShiftValidator | `KRITIEKE_SHIFT` | ERROR | Alle kritieke shifts per dag ingevuld |
| DubbeleShiftValidator | `DUBBELE_SHIFT` | WARNING | Geen dubbele toewijzingen per dag |
| RodeLijnValidator | `RODE_LIJN_MAX_WERK` | WARNING | Max 19 werkdagen per 28-daagse cyclus |
| MaxDagenOpRijValidator | `MAX_DAGEN_OP_RIJ` | ERROR | Max 7 consecutieve werkdagen |
| MaxUrenPerWeekValidator | `MAX_UREN_PER_WEEK` | WARNING | Max 50 uur per week |
| MinRusttijdValidator | `MIN_RUSTTIJD` | ERROR | Min 11 uur rust tussen shifts |
| NachtshiftOpvolgingValidator | `NACHT_OPVOLGING` | CRITICAL | Na nacht geen vroege/dag shift |
| MaxWeekendsOpRijValidator | `MAX_WEEKENDS_OP_RIJ` | WARNING | Max 6 weekends achter elkaar |
| RXGapValidator | `RX_GAP` | WARNING | Max dagen tussen RX rustdagen |
| RXFDeadlineValidator | `RXF_DEADLINE` | WARNING | RXF deadline controle |

### Ernst Niveaus

```python
class RegelErnst(str, Enum):
    CRITICAL = "CRITICAL"  # Blokkerend - mag niet worden opgeslagen
    ERROR = "ERROR"        # Serieus - vereist aandacht
    WARNING = "WARNING"    # Waarschuwing - informatief
```

### Validator Details

#### KritiekeShiftValidator
- **Bestand:** `kritieke_shift_validator.py`
- **Regel:** Alle als "kritiek" gemarkeerde shifts moeten elke dag ingevuld zijn
- **Scope:** Dag-niveau (controleert per datum)

#### DubbeleShiftValidator
- **Bestand:** `dubbele_shift_validator.py`
- **Regel:** Een medewerker mag niet twee shifts op dezelfde dag hebben
- **Scope:** Dag-niveau per gebruiker

#### RodeLijnValidator
- **Bestand:** `rode_lijn_validator.py`
- **Regel:** Max 19 werkdagen per 28-daagse cyclus (rode lijn periodes)
- **Config:** `rode_lijn_start`, `rode_lijn_interval` uit HRConfig
- **Context nodig:** Tot vorige rode lijn (max 28 dagen terug)

#### MaxDagenOpRijValidator
- **Bestand:** `max_dagen_op_rij_validator.py`
- **Regel:** Max 7 consecutieve werkdagen
- **Context nodig:** 7 dagen terug

#### MaxUrenPerWeekValidator
- **Bestand:** `max_uren_per_week_validator.py`
- **Regel:** Max 50 uur per kalenderweek
- **Gebruikt:** `uren_per_shift` uit shift metadata

#### MinRusttijdValidator
- **Bestand:** `min_rusttijd_validator.py`
- **Regel:** Min 11 uur rust tussen einde shift en begin volgende
- **Gebruikt:** `start_tijd`, `eind_tijd` uit shift metadata

#### NachtshiftOpvolgingValidator
- **Bestand:** `nachtshift_opvolging_validator.py`
- **Regel:** Na nachtshift mag eerste werkshift geen vroege of dagdienst zijn
- **Late shift grens:** >= 14:00
- **Context nodig:** Tot laatste nachtshift (variabel)

#### MaxWeekendsOpRijValidator
- **Bestand:** `max_weekends_op_rij_validator.py`
- **Regel:** Max 6 opeenvolgende weekends werken
- **Context nodig:** 42 dagen terug (6 weekends)

#### RXGapValidator
- **Bestand:** `rx_gap_validator.py`
- **Regel:** Max aantal dagen tussen RX rustdagen
- **Config:** Configureerbaar via HR regels

---

## ValidatieContext

> **Let op:** Dit is een geplande verbetering. Zie `docs/plannen/plan_validatie_context.md`

### Probleem

De huidige `valideer_maandplanning()` haalt alleen shifts van de gevraagde maand op. Dit mist context voor maandovergangen:
- Nacht 31 maart + Vroeg 1 april → niet gedetecteerd
- 6 werkdagen eind maart + 2 april → 8 op rij niet gedetecteerd

### Oplossing

`ValidatieContext` dataclass met start-state per gebruiker:

```python
@dataclass
class ValidatieContext:
    """Start-state voor een gebruiker bij maandvalidatie."""
    gebruiker_id: int
    weekends_op_rij: int = 0
    werkdagen_sinds_rode_lijn: int = 0
    laatste_shift_was_nacht: bool = False
    dagen_sinds_laatste_rx: int = 0
    werkdagen_op_rij: int = 0
    laatste_shift_eind_tijd: Optional[datetime] = None
```

Context wordt berekend uit shifts van vorige 42 dagen, validators gebruiken dit als startpunt.

---

## HRConfig

Centrale configuratie voor alle validators.

```python
@dataclass
class HRConfig:
    """Configuratie voor HR-regelvalidatie."""
    regels: Dict[str, Dict[str, Any]]      # Code -> regel data
    shift_tijden: Dict[str, Dict[str, Any]] # Shiftcode -> tijden/metadata
    rode_lijn_start: date = date(2026, 1, 1)
    rode_lijn_interval: int = 28

    def haal_regel_waarde(self, regel_code: str, default: Any = None) -> Any:
        """Haal regelwaarde op (bijv. max_dagen)."""
        ...

    def haal_regel_ernst(self, regel_code: str, default: str = "WARNING") -> str:
        """Haal ernst niveau op voor een regel."""
        ...

    def haal_shift_metadata(self, shiftcode: str) -> Optional[Dict[str, Any]]:
        """Haal shift metadata op (tijden, is_nachtshift, etc.)."""
        ...
```

### Shift Metadata

| Veld | Type | Beschrijving |
|------|------|--------------|
| `start_tijd` | time | Starttijd van shift |
| `eind_tijd` | time | Eindtijd van shift |
| `is_nachtshift` | bool | True voor nachtshifts |
| `is_rustdag` | bool | True voor rustdagen (RX, Z, etc.) |
| `rustdag_type` | str | Type rustdag (RXW, RXF, etc.) |
| `telt_als_werkdag` | bool | Telt mee voor werkdagen telling |
| `uren_per_shift` | float | Aantal uren per shift |

---

## Service API

### HRValidatieService

```python
class HRValidatieService:
    """Orchestreert HR-regelvalidatie."""

    @classmethod
    def haal_hr_config(cls, force_refresh: bool = False) -> HRConfig:
        """Haal HR configuratie op (gecached)."""

    @classmethod
    def valideer_maandplanning(
        cls, jaar: int, maand: int, force_refresh: bool = False
    ) -> ValidatieRapport:
        """Valideer volledige maandplanning (batch)."""

    @classmethod
    def valideer_enkele_shift(
        cls,
        gebruiker_id: int,
        datum: date,
        shift_code: str,
        extra_wijzigingen: Optional[Dict[Tuple[int, str], str]] = None,
        periode_context: Optional[Tuple[date, date]] = None,
    ) -> List[RegelOvertreding]:
        """Valideer één hypothetische shift (voor suggesties)."""

    @classmethod
    def valideer_met_shifts(
        cls, shifts_data: List[Dict[str, Any]], cache_key: Optional[tuple] = None
    ) -> ValidatieRapport:
        """Valideer shifts in-memory (voor realtime feedback)."""

    @classmethod
    def invalideer_cache(cls, jaar: int, maand: int) -> None:
        """Invalideer validatie cache voor specifieke maand."""

    @classmethod
    def invalideer_config_cache(cls) -> None:
        """Invalideer HR configuratie cache."""

    @classmethod
    def invalideer_alle_cache(cls) -> None:
        """Invalideer volledige validatie cache."""
```

---

## Domein Objecten

### PlanningShift

```python
@dataclass
class PlanningShift:
    """Shift voor HR-validatie (domein object)."""
    id: int
    planning_id: int
    gebruiker_id: int
    datum: date
    shiftcode: str
    start_tijd: Optional[time] = None
    eind_tijd: Optional[time] = None
    is_nachtshift: bool = False
    is_rustdag: bool = False
    rustdag_type: Optional[str] = None
    telt_als_werkdag: bool = True
    uren_per_shift: Optional[float] = None

    @classmethod
    def van_database_row(cls, row: Dict, metadata: Dict) -> "PlanningShift":
        """Factory method vanuit database row + metadata."""
```

### RegelOvertreding

```python
@dataclass
class RegelOvertreding:
    """Eén overtreding van een HR-regel."""
    regel_code: str
    regel_naam: str
    gebruiker_id: int
    datum: date
    bericht: str
    ernst: str = "WARNING"
    datum_tot: Optional[date] = None      # Voor periode-overtredingen
    betrokken_shifts: List[int] = field(default_factory=list)
```

### ValidatieRapport

```python
@dataclass
class ValidatieRapport:
    """Verzameling van alle overtredingen."""
    overtredingen: List[RegelOvertreding] = field(default_factory=list)

    @property
    def is_geldig(self) -> bool:
        """True als geen ERROR of CRITICAL overtredingen."""

    def voeg_toe(self, overtreding: RegelOvertreding) -> None:
        """Voeg één overtreding toe."""

    def voeg_toe_bulk(self, overtredingen: List[RegelOvertreding]) -> None:
        """Voeg meerdere overtredingen toe."""

    def filter_gebruiker(self, gebruiker_id: int) -> "ValidatieRapport":
        """Filter op gebruiker."""

    def filter_ernst(self, *ernst_levels: str) -> "ValidatieRapport":
        """Filter op ernst niveau(s)."""
```

---

## Gebruik in Code

### Maandplanning Valideren

```python
from src.services.applicatie.hr_validatie_service import HRValidatieService

# Valideer april 2026
rapport = HRValidatieService.valideer_maandplanning(2026, 4)

if not rapport.is_geldig:
    for overtreding in rapport.overtredingen:
        print(f"{overtreding.ernst}: {overtreding.bericht}")
```

### Enkele Shift Valideren (voor suggesties)

```python
# Check of shift toegewezen kan worden
overtredingen = HRValidatieService.valideer_enkele_shift(
    gebruiker_id=123,
    datum=date(2026, 4, 15),
    shift_code="D"
)

if overtredingen:
    print("Shift niet toegestaan:")
    for o in overtredingen:
        print(f"  - {o.bericht}")
```

### Realtime Validatie (in-memory)

```python
# Converteer planning naar HR formaat
shifts_data = HRValidatieService.converteer_planning_naar_hr_shifts(
    planning_shifts,
    wijzigingen=onopgeslagen_wijzigingen
)

# Valideer zonder database
rapport = HRValidatieService.valideer_met_shifts(shifts_data)
```

### Cache Invalideren

```python
# Na opslaan van wijzigingen
HRValidatieService.invalideer_cache(2026, 4)

# Na wijzigen HR regels
HRValidatieService.invalideer_config_cache()
```

---

## Referenties

- `docs/plannen/plan_validatie_context.md` - ValidatieContext implementatieplan
- `docs/referentie/database_schema.md` - HR regel tabellen
- `docs/referentie/services_api.md` - Overige services