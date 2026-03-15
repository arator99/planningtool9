# Domein Objecten Referentie

**Versie:** 0.7.x
**Laatst bijgewerkt:** 2026-03-11
**Doel:** Complete referentie van alle domein objecten (dataclasses) en business logic functies

---

## 📋 Inhoudsopgave

1. [Introductie](#introductie)
2. [Algemene Principes](#algemene-principes)
3. [Gebruiker & Authenticatie](#gebruiker--authenticatie)
4. [Rollen & Autorisatie](#rollen--autorisatie)
5. [Referentiedata](#referentiedata)
6. [Planning](#planning)
7. [Verlof](#verlof)
8. [Notities](#notities)
9. [HR-Regelvalidatie](#hr-regelvalidatie) → Zie ook [hr_validatie.md](./hr_validatie.md)
10. [Auto-Scheduling](#auto-scheduling)
11. [Validatie Functies](#validatie-functies)
12. [Common Patterns](#common-patterns)

---

## Introductie

### Wat zijn Domein Objecten?

Domein objecten (dataclasses) zijn pure Python objecten die business data en regels representeren **zonder database of UI afhankelijkheden**. Ze vormen het hart van de 3-laags architectuur:

```
GUI (PyQt6) → Applicatie Service → Domein Logica (dit document) ← Repo (SQL)
```

### Locatie

Alle domein objecten bevinden zich in `src/services/domein/`:

**Basis domein:**
- `gebruiker.py`, `gebruiker_domein.py` — Gebruiker dataclasses
- `authenticatie_domein.py` — Login, sessie
- `rol_domein.py` — Rollen en permissies
- `post_domein.py` — Werkposten
- `shiftcode_domein.py` — Shift codes
- `typetabel_domein.py` — Typetabellen
- `planning_domein.py` — Planning shifts
- `verlof_domein.py` — Verlof aanvragen
- `notitie_domein.py` — Notities
- `logboek_domein.py` — Audit logging

**HR Validatie:**
- `hr_regel_domein.py` — HRConfig, PlanningShift, RegelOvertreding
- `validators/` — 10 validators (zie [hr_validatie.md](./hr_validatie.md))

**Auto-Scheduling:**
- `auto_scheduling_domein.py` — Toewijzingen, constraints
- `suggestie_domein.py` — Shift suggesties
- `shift_type_domein.py` — Shift type classificatie
- `shift_type_detectie.py` — Detectie algoritme
- `rustdag_generator.py` — Rustdag generatie
- `planning_context_domein.py` — Planning context
- `rotatie_domein.py` — Rotatie patronen

**Overig:**
- `feestdagen_domein.py` — Feestdagen
- `heatmap_domein.py` — Heatmap data
- `adv_domein.py` — ADV berekeningen
- `exceptions.py` — Domein exceptions

---

## Algemene Principes

### Factory Pattern

Alle dataclasses hebben een `van_database_row()` class method:

```python
@classmethod
def van_database_row(cls, row: Dict[str, Any]) -> 'Object':
    """Creëer domein object uit database row (Dict)."""
    return cls(
        id=row['id'],
        naam=row['naam'],
        # ... mapping
    )
```

**KRITIEK:** Object mapping gebeurt IN de domein laag, NIET in repo. Repo retourneert altijd `Dict[str, Any]`.

### Naar Database Conversie

Sommige objecten hebben een `naar_database_dict()` methode voor inserts/updates:

```python
def naar_database_dict(self) -> Dict[str, Any]:
    """Converteer object naar dict voor database operaties."""
    return {
        'gebruiker_id': self.gebruiker_id,
        'datum': self.datum,
        # ... zonder id (auto-increment)
    }
```

### Type Hints

Alle domein objecten gebruiken **verplichte type hints**:
- `str`, `int`, `bool`, `float`
- `Optional[T]` voor nullable velden
- `List[T]` voor lijsten
- `Dict[K, V]` voor dictionaries
- `date`, `time`, `datetime` uit `datetime` module

---

## Gebruiker & Authenticatie

### `Gebruiker` (gebruiker.py)

**Gebruik:** Basis gebruiker object voor sessies en authenticatie.

```python
@dataclass
class Gebruiker:
    id: int
    gebruiker_uuid: str
    gebruikersnaam: str
    volledige_naam: str
    voornaam: str
    achternaam: str
    rol: str
    is_actief: bool = True
```

#### Database Mapping

| Attribuut | Database Veld | Type | Opmerking |
|-----------|--------------|------|-----------|
| `id` | `gebruikers.id` | INTEGER | Primary key |
| `gebruiker_uuid` | `gebruikers.gebruiker_uuid` | TEXT | UUID v4 |
| `gebruikersnaam` | `gebruikers.gebruikersnaam` | TEXT | Uniek |
| `volledige_naam` | `gebruikers.volledige_naam` | TEXT | Belgisch formaat: "Achternaam Voornaam" |
| `voornaam` | `gebruikers.voornaam` | TEXT | - |
| `achternaam` | `gebruikers.achternaam` | TEXT | - |
| `rol` | `gebruikers.rol` | TEXT | 'teamlid', 'planner', 'beheerder', 'admin' |
| `is_actief` | `gebruikers.is_actief` | BOOLEAN | Default 1 |

#### Factory Method

```python
gebruiker = Gebruiker.van_database_row(row)
```

#### Extra Methods

```python
# Conversie naar sessie data
sessie_data = gebruiker.naar_sessie_data()
# => {'id': 1, 'gebruikersnaam': 'jan.peeters', ...}

# Rol check
if gebruiker.heeft_rol('planner'):
    # ... planner functionaliteit
```

#### Gebruik Voorbeeld

```python
from src.services.repo.gebruiker_repo import GebruikerRepo
from src.services.domein.gebruiker import Gebruiker

# Repo retourneert Dict
row = GebruikerRepo.haal_gebruiker_op_naam("jan.peeters")

# Domein mapping
gebruiker = Gebruiker.van_database_row(row)

# Gebruik domein object
print(f"Welkom {gebruiker.volledige_naam}!")  # "Welkom Peeters Jan!"
```

---

### `GebruikerVolledig` (gebruiker.py)

**Gebruik:** Uitgebreide gebruiker met alle database velden voor gebruikersbeheer scherm.

```python
@dataclass
class GebruikerVolledig(Gebruiker):
    is_reserve: bool = False
    startweek_typedienst: Optional[int] = None
    shift_voorkeuren: Optional[str] = None
    theme_voorkeur: str = 'light'
    aangemaakt_op: Optional[str] = None
    gedeactiveerd_op: Optional[str] = None
    laatste_login: Optional[str] = None
```

#### Database Mapping (Extra Velden)

| Attribuut | Database Veld | Type | Opmerking |
|-----------|--------------|------|-----------|
| `is_reserve` | `gebruikers.is_reserve` | BOOLEAN | Reserve medewerker |
| `startweek_typedienst` | `gebruikers.startweek_typedienst` | INTEGER | Week 1-6 |
| `shift_voorkeuren` | `gebruikers.shift_voorkeuren` | TEXT | JSON string |
| `theme_voorkeur` | `gebruikers.theme_voorkeur` | TEXT | 'light' of 'dark' |
| `aangemaakt_op` | `gebruikers.aangemaakt_op` | TEXT | ISO timestamp |
| `gedeactiveerd_op` | `gebruikers.gedeactiveerd_op` | TEXT | ISO timestamp |
| `laatste_login` | `gebruikers.laatste_login` | TEXT | ISO timestamp |

#### Factory Method

```python
gebruiker_volledig = GebruikerVolledig.van_database_row_volledig(row)
```

#### Extra Methods

```python
# Conversie naar dict (voor JSON/debugging)
data = gebruiker_volledig.naar_dict()
```

---

### Gebruiker Validatie Functies (gebruiker_domein.py)

**GEEN dataclass** - Pure business logic functies.

#### `valideer_gebruiker_data()`

```python
def valideer_gebruiker_data(
    gebruikersnaam: str,
    volledige_naam: str,
    voornaam: str,
    achternaam: str,
    rol: str
) -> Tuple[bool, Optional[str]]:
    """
    Valideert gebruiker basis data volgens business rules.

    Returns:
        (True, None) als geldig
        (False, "foutmelding") als ongeldig
    """
```

**Business Rules:**
- Gebruikersnaam: min 3, max 50 chars, alleen alphanumeriek + `_.`
- Volledige naam: verplicht, max 100 chars
- Voornaam/Achternaam: verplicht, max 50 chars
- Rol: moet een van `['teamlid', 'planner', 'beheerder', 'admin']` zijn

#### `genereer_volledige_naam()`

```python
def genereer_volledige_naam(voornaam: str, achternaam: str) -> str:
    """
    Belgische standaard: Achternaam Voornaam.

    Returns:
        "Peeters Jan" (niet "Jan Peeters")
    """
```

#### `mag_gebruiker_deactiveren()`

```python
def mag_gebruiker_deactiveren(
    gebruiker_id: int,
    huidige_gebruiker_id: int
) -> Tuple[bool, Optional[str]]:
    """
    Business regel: Een gebruiker mag zichzelf niet deactiveren.
    """
```

---

## Rollen & Autorisatie

### `Rol` (rol_domein.py)

**Gebruik:** Rol definitie met hiërarchie niveau voor toegangscontrole.

```python
@dataclass
class Rol:
    code: str           # 'teamlid', 'planner', 'beheerder', 'admin'
    naam: str           # 'Teamlid', 'Planner', 'Beheerder', 'Administrator'
    beschrijving: str   # Uitgebreide beschrijving
    niveau: int         # Hiërarchie niveau (1=laagst, 4=hoogst)
```

#### Hiërarchie

| Code | Naam | Niveau | Beschrijving |
|------|------|--------|-------------|
| `teamlid` | Teamlid | 1 | Basis gebruiker, eigen rooster bekijken |
| `planner` | Planner | 2 | Roosters plannen en beheren |
| `beheerder` | Beheerder | 3 | Gebruikers beheren, systeem configuratie |
| `admin` | Administrator | 4 | Volledige toegang |

#### Method: `heeft_toegang_tot()`

```python
rol = Rol(code='planner', naam='Planner', beschrijving='...', niveau=2)

if rol.heeft_toegang_tot('teamlid'):
    # True - hogere niveaus hebben toegang tot lagere
```

**Regel:** Hoger niveau = toegang tot lager niveau functionaliteit.

#### Rol Functies

```python
# Haal alle rollen op
rollen = get_alle_rollen()
# => [Rol(teamlid, ...), Rol(planner, ...), ...]

# Haal specifieke rol op
rol = get_rol('planner')
# => Rol(code='planner', naam='Planner', ...)

# Check geldigheid
is_geldig = is_geldige_rol('planner')  # True
is_geldig = is_geldige_rol('unknown')  # False

# Validatie met feedback
is_geldig, fout = valideer_rol('planner')
# => (True, None)

# Niveau vergelijking
heeft_hoger_niveau = rol_heeft_hoger_niveau('admin', 'planner')
# => True (admin niveau 4 > planner niveau 2)

# Toegestane rollen
toegestaan = get_toegestane_rollen_voor('beheerder')
# => [Rol(teamlid), Rol(planner), Rol(beheerder)]  (niveau <= 3)
```

---

## Referentiedata

### `Post` (post_domein.py)

**Gebruik:** Werkpost/functie binnen het team (bijv. "Operatie", "Controle").

```python
@dataclass
class Post:
    id: int
    naam: str
    beschrijving: Optional[str]
    telt_als_werkdag: bool
    reset_12u_rust: bool
    breekt_werk_reeks: bool
    is_actief: bool
    aangemaakt_op: str
    gedeactiveerd_op: Optional[str]
```

#### Database Mapping

| Attribuut | Database Veld | Type | Opmerking |
|-----------|--------------|------|-----------|
| `id` | `werkposten.id` | INTEGER | Primary key |
| `naam` | `werkposten.naam` | TEXT | **LET OP:** Geen `code` veld! |
| `beschrijving` | `werkposten.beschrijving` | TEXT | Nullable |
| `telt_als_werkdag` | `werkposten.telt_als_werkdag` | BOOLEAN | Voor HR-regels |
| `reset_12u_rust` | `werkposten.reset_12u_rust` | BOOLEAN | Voor HR-regels |
| `breekt_werk_reeks` | `werkposten.breekt_werk_reeks` | BOOLEAN | Voor HR-regels |
| `is_actief` | `werkposten.is_actief` | BOOLEAN | Soft delete |
| `aangemaakt_op` | `werkposten.aangemaakt_op` | TEXT | ISO timestamp |
| `gedeactiveerd_op` | `werkposten.gedeactiveerd_op` | TEXT | ISO timestamp |

#### ⚠️ KRITIEKE MAPPING ISSUE

**VERKEERD:**
```python
# ❌ Post heeft GEEN 'code' attribuut!
code = post.code  # AttributeError!
```

**CORRECT:**
```python
# ✅ Post heeft alleen 'naam'
naam = post.naam
```

#### Factory Method

```python
post = Post.van_database_row(row)
```

#### Validatie Functies

```python
# Valideer post data
is_geldig, fout = valideer_post_data(
    naam="Operatie",
    beschrijving="Operationele taken"
)
# => (True, None)

# Genereer weergavenaam
weergave = genereer_post_weergave_naam("  operatie  ")
# => "Operatie" (getrimmed + capitalized)
```

---

### `Competentie` (competentie_domein.py)

**Gebruik:** Vaardigheid/kwalificatie van medewerker (bijv. "EHBO", "Heftruckcertificaat").

```python
@dataclass
class Competentie:
    id: int
    naam: str
    beschrijving: Optional[str]
    categorie: Optional[str]
    is_actief: bool
    aangemaakt_op: str
    gedeactiveerd_op: Optional[str]
```

#### Database Mapping

| Attribuut | Database Veld | Type | Opmerking |
|-----------|--------------|------|-----------|
| `id` | `competenties.id` | INTEGER | Primary key |
| `naam` | `competenties.naam` | TEXT | Uniek |
| `beschrijving` | `competenties.beschrijving` | TEXT | Nullable |
| `categorie` | `competenties.categorie` | TEXT | Bijv. "Certificaat", "Vaardigheid" |
| `is_actief` | `competenties.is_actief` | BOOLEAN | Soft delete |
| `aangemaakt_op` | `competenties.aangemaakt_op` | TEXT | ISO timestamp |
| `gedeactiveerd_op` | `competenties.gedeactiveerd_op` | TEXT | ISO timestamp |

#### Factory Method

```python
competentie = Competentie.van_database_row(row)
```

#### Validatie Functies

```python
# Valideer competentie data
is_geldig, fout = valideer_competentie_data(
    naam="EHBO",
    beschrijving="Eerste Hulp Bij Ongelukken",
    categorie="Certificaat"
)
# => (True, None)

# Genereer weergavenaam
weergave = genereer_competentie_weergave_naam("  ehbo  ")
# => "Ehbo" (title case)
```

---

### `Shiftcode` (shiftcode_domein.py)

**Gebruik:** Dienst code met tijden en metadata (bijv. "DE" = Dagdienst Early).

```python
@dataclass
class Shiftcode:
    id: int
    werkpost_id: Optional[int]
    dag_type: Optional[str]      # 'werkdag', 'weekend', 'feestdag'
    shift_type: Optional[str]    # 'early', 'late', 'night'
    code: str                    # "DE", "DL", "DN"
    start_uur: Optional[str]     # "06:00"
    eind_uur: Optional[str]      # "14:00"
    is_kritisch: bool            # Moet altijd bezet zijn
```

#### Database Mapping

| Attribuut | Database Veld | Type | Opmerking |
|-----------|--------------|------|-----------|
| `id` | `shiftcodes.id` | INTEGER | Primary key |
| `werkpost_id` | `shiftcodes.werkpost_id` | INTEGER | FK naar werkposten |
| `dag_type` | `shiftcodes.dag_type` | TEXT | Nullable |
| `shift_type` | `shiftcodes.shift_type` | TEXT | **LET OP:** Niet `beschrijving`! |
| `code` | `shiftcodes.code` | TEXT | Uniek, max 10 chars |
| `start_uur` | `shiftcodes.start_uur` | TEXT | **LET OP:** Niet `start_tijd`! |
| `eind_uur` | `shiftcodes.eind_uur` | TEXT | **LET OP:** Niet `eind_tijd`! |
| `is_kritisch` | `shiftcodes.is_kritisch` | BOOLEAN | **LET OP:** Niet `is_actief`! |

#### ⚠️ KRITIEKE MAPPING ISSUES

**VERKEERDE VELDNAMEN:**
```python
# ❌ Deze attributen bestaan NIET!
beschrijving = shift.beschrijving  # AttributeError!
start_tijd = shift.start_tijd      # AttributeError!
eind_tijd = shift.eind_tijd        # AttributeError!
diensttype = shift.diensttype      # AttributeError!
is_actief = shift.is_actief        # AttributeError!
```

**CORRECTE VELDNAMEN:**
```python
# ✅ Gebruik deze attributen
shift_type = shift.shift_type      # "early", "late", "night"
start_uur = shift.start_uur        # "06:00"
eind_uur = shift.eind_uur          # "14:00"
dag_type = shift.dag_type          # "werkdag", "weekend"
is_kritisch = shift.is_kritisch    # True/False
```

#### Factory Method

```python
shiftcode = Shiftcode.van_database_row(row)
```

#### Validatie Functies

```python
# Valideer shiftcode data
is_geldig, fout = valideer_shiftcode_data(
    code="DE",
    start_uur="06:00",
    eind_uur="14:00"
)
# => (True, None)

# Genereer weergavenaam
weergave = genereer_shiftcode_weergave_naam("de")
# => "DE" (uppercase)
```

---

## Planning

### `PlanningShift` (planning_domein.py)

**Gebruik:** Individuele shift voor één gebruiker op één dag.

**⚠️ KRITIEK - VELDNAAM:** Deze klasse gebruikt `shift_code` (met underscore). Gebruik NOOIT `shift.shiftcode` - dit attribuut bestaat niet en geeft AttributeError!

```python
@dataclass
class PlanningShift:
    id: Optional[int]
    gebruiker_id: int
    datum: str                    # ISO format: "YYYY-MM-DD"
    shift_code: Optional[str]     # ✅ MET underscore! None = vrije dag
    notitie: Optional[str]
    notitie_gelezen: bool
    status: str                   # 'concept' of 'gepubliceerd'
    aangemaakt_op: Optional[str]
```

#### Database Mapping

| Attribuut | Database Veld | Type | Opmerking |
|-----------|--------------|------|-----------|
| `id` | `planning.id` | INTEGER | Primary key, None voor nieuwe shifts |
| `gebruiker_id` | `planning.gebruiker_id` | INTEGER | FK naar gebruikers |
| `datum` | `planning.datum` | TEXT | ISO format YYYY-MM-DD |
| `shift_code` | `planning.shift_code` | TEXT | Nullable (None = vrije dag) |
| `notitie` | `planning.notitie` | TEXT | Nullable |
| `notitie_gelezen` | `planning.notitie_gelezen` | BOOLEAN | Default 0 |
| `status` | `planning.status` | TEXT | 'concept' of 'gepubliceerd' |
| `aangemaakt_op` | `planning.aangemaakt_op` | TEXT | ISO timestamp |

#### Factory Method

```python
shift = PlanningShift.van_database_row(row)
```

#### Conversie naar Database

```python
data = shift.naar_database_dict()
# => {'gebruiker_id': 1, 'datum': '2026-01-15', 'shift_code': 'DE', ...}
# Let op: Geen 'id' en 'aangemaakt_op' (auto-generated)
```

#### Validatie Functies

```python
# Valideer shift data
is_geldig, fout = valideer_planning_shift(
    gebruiker_id=1,
    datum="2026-01-15",
    shift_code="DE"
)
# => (True, None)

# Valideer status
is_geldig, fout = valideer_planning_status("gepubliceerd")
# => (True, None)
```

---

### `MaandPlanning` (planning_domein.py)

**Gebruik:** Aggregaat van alle shifts voor een specifieke maand.

```python
@dataclass
class MaandPlanning:
    jaar: int
    maand: int                          # 1-12
    shifts: List[PlanningShift]
    status: str = 'concept'             # Overall status
```

#### Methods

```python
planning = MaandPlanning(jaar=2026, maand=1, shifts=[...])

# Haal specifieke shift op
shift = planning.haal_shift(gebruiker_id=1, datum="2026-01-15")
# => PlanningShift of None

# Haal alle shifts voor gebruiker
shifts = planning.haal_shifts_voor_gebruiker(gebruiker_id=1)
# => [PlanningShift, PlanningShift, ...]

# Haal alle shifts voor datum
shifts = planning.haal_shifts_voor_datum(datum="2026-01-15")
# => [PlanningShift, PlanningShift, ...]
```

#### Helper Functies

```python
# Genereer alle datums voor een maand
datums = genereer_maand_datums(jaar=2026, maand=1)
# => ["2026-01-01", "2026-01-02", ..., "2026-01-31"]
```

---

## Verlof

### `VerlofType` (verlof_domein.py)

**Gebruik:** Type verlof met metadata (bijv. "VV" = Verlof, "KD" = Kompensatiedag).

```python
@dataclass
class VerlofType:
    id: int
    code: str                    # "VV", "KD", "RX", "CX", "Z"
    naam: str                    # "Verlof", "Kompensatiedag"
    term: Optional[str]          # "verlof", "kompensatiedag"
    telt_als_werkdag: bool
    reset_12u_rust: bool
    breekt_werk_reeks: bool
```

#### Database Mapping

| Attribuut | Database Veld | Type | Opmerking |
|-----------|--------------|------|-----------|
| `id` | `verlof_types.id` | INTEGER | Primary key |
| `code` | `verlof_types.code` | TEXT | Uniek, max 10 chars |
| `naam` | `verlof_types.naam` | TEXT | Weergavenaam |
| `term` | `verlof_types.term` | TEXT | Voor categorisatie |
| `telt_als_werkdag` | `verlof_types.telt_als_werkdag` | BOOLEAN | Voor HR-regels |
| `reset_12u_rust` | `verlof_types.reset_12u_rust` | BOOLEAN | Voor HR-regels |
| `breekt_werk_reeks` | `verlof_types.breekt_werk_reeks` | BOOLEAN | Voor HR-regels |

#### Factory Method

```python
verlof_type = VerlofType.van_database_row(row)
```

---

### `VerlofAanvraag` (verlof_domein.py)

**Gebruik:** Verlofaanvraag met status en behandeling.

```python
@dataclass
class VerlofAanvraag:
    id: Optional[int]
    gebruiker_id: int
    start_datum: str                      # ISO format: "YYYY-MM-DD"
    eind_datum: str
    aantal_dagen: int
    status: str                           # 'pending', 'goedgekeurd', 'geweigerd'
    toegekende_code_term: Optional[str]   # Verloftype term
    opmerking: Optional[str]
    aangevraagd_op: Optional[str]
    behandeld_door: Optional[int]
    behandeld_op: Optional[str]
    reden_weigering: Optional[str]
```

**⚠️ KRITIEK - Status waarden:**
De database heeft een CHECK constraint op status. Gebruik ALLEEN deze waarden:
- `'pending'` - Openstaand (wacht op behandeling)
- `'goedgekeurd'` - Goedgekeurd door planner/beheerder
- `'geweigerd'` - Geweigerd door planner/beheerder

#### Database Mapping

| Attribuut | Database Veld | Type | Opmerking |
|-----------|--------------|------|-----------|
| `id` | `verlof_aanvragen.id` | INTEGER | Primary key |
| `gebruiker_id` | `verlof_aanvragen.gebruiker_id` | INTEGER | FK naar gebruikers |
| `start_datum` | `verlof_aanvragen.start_datum` | TEXT | ISO format |
| `eind_datum` | `verlof_aanvragen.eind_datum` | TEXT | ISO format |
| `aantal_dagen` | `verlof_aanvragen.aantal_dagen` | INTEGER | Inclusief start en eind |
| `status` | `verlof_aanvragen.status` | TEXT | 'pending', 'goedgekeurd', 'geweigerd' (CHECK constraint) |
| `toegekende_code_term` | `verlof_aanvragen.toegekende_code_term` | TEXT | Nullable |
| `opmerking` | `verlof_aanvragen.opmerking` | TEXT | Nullable |
| `aangevraagd_op` | `verlof_aanvragen.aangevraagd_op` | TEXT | ISO timestamp |
| `behandeld_door` | `verlof_aanvragen.behandeld_door` | INTEGER | FK naar gebruikers |
| `behandeld_op` | `verlof_aanvragen.behandeld_op` | TEXT | ISO timestamp |
| `reden_weigering` | `verlof_aanvragen.reden_weigering` | TEXT | Bij afwijzing |

#### Factory Method

```python
aanvraag = VerlofAanvraag.van_database_row(row)
```

#### Conversie naar Database

```python
data = aanvraag.naar_database_dict()
# => {'gebruiker_id': 1, 'start_datum': '2026-01-15', ...}
```

#### Validatie Functies

```python
# Valideer aanvraag data
is_geldig, fout = valideer_verlof_aanvraag(
    gebruiker_id=1,
    start_datum="2026-01-15",
    eind_datum="2026-01-20",
    aantal_dagen=6
)
# => (True, None)

# Valideer status
is_geldig, fout = valideer_verlof_status("goedgekeurd")
# => (True, None)

# Bereken aantal dagen
dagen = bereken_aantal_dagen("2026-01-15", "2026-01-20")
# => 6 (inclusief start en eind)
```

---

### `VerlofFifoVerdeling` (verlof_saldo_service.py)

**Gebruik:** FIFO-verdeling van verlof over huidig jaar en vorig jaar (overgedragen) potten.

**Context:** Overgedragen dagen vervallen op 1 mei. FIFO (First In, First Out) zorgt ervoor dat opgenomen/aangevraagde dagen eerst van de overgedragen pot worden afgetrokken.

```python
@dataclass
class VerlofFifoVerdeling:
    # Vorig jaar pot (overgedragen)
    vorig_jaar_recht: int           # Oorspronkelijk overgedragen
    vorig_jaar_aangevraagd: int     # Aangevraagd uit deze pot (FIFO)
    vorig_jaar_opgenomen: int       # Opgenomen uit deze pot (FIFO)
    vorig_jaar_beschikbaar: int     # Restant (recht - aangevraagd - opgenomen)

    # Huidig jaar pot
    huidig_jaar_recht: int          # Totaal recht dit jaar
    huidig_jaar_aangevraagd: int    # Aangevraagd uit deze pot (FIFO)
    huidig_jaar_opgenomen: int      # Opgenomen uit deze pot (FIFO)
    huidig_jaar_beschikbaar: int    # Restant
```

#### Veld Definities

| Veld | Definitie |
|------|-----------|
| `recht` | Totaal toegewezen dagen voor die pot |
| `aangevraagd` | Dagen in actieve aanvragen (pending + goedgekeurd) met toekomstige datum |
| `opgenomen` | Dagen met VV/KD code op planning waar datum < vandaag |
| `beschikbaar` | `recht - aangevraagd - opgenomen` |

#### FIFO Logica

```
Voorbeeld: 22 overgedragen, 25 huidig jaar recht, 36 opgenomen

FIFO verdeling opgenomen:
- Vorig jaar opgenomen: min(22, 36) = 22  (pot is leeg)
- Huidig jaar opgenomen: 36 - 22 = 14

Resultaat:
- Vorig jaar beschikbaar: 22 - 0 - 22 = 0
- Huidig jaar beschikbaar: 25 - 0 - 14 = 11
```

#### Properties

```python
fifo = VerlofFifoVerdeling(...)

# Totalen (som van beide potten)
totaal_recht = fifo.totaal_recht           # vorig + huidig
totaal_aangevraagd = fifo.totaal_aangevraagd
totaal_opgenomen = fifo.totaal_opgenomen
totaal_beschikbaar = fifo.totaal_beschikbaar
```

#### Gebruik Voorbeeld

```python
from src.services.applicatie.verlof_saldo_service import (
    VerlofSaldoService, VerlofFifoVerdeling
)

# Bereken FIFO verdeling voor VV (verlof)
fifo = VerlofSaldoService.bereken_fifo_verdeling(
    gebruiker_id=1, jaar=2026, verlof_type="VV"
)

# Check of er nog overgedragen dagen resteren
if fifo.vorig_jaar_beschikbaar > 0:
    print(f"⚠ Nog {fifo.vorig_jaar_beschikbaar} dagen voor 1 mei op te nemen!")
elif fifo.vorig_jaar_recht > 0:
    print("✓ Overgedragen dagen volledig opgenomen")
```

---

## Notities

### `Notitie` (notitie_domein.py)

**Gebruik:** Melding/bericht tussen gebruikers met prioriteit.

```python
@dataclass
class Notitie:
    id: Optional[int]
    van_gebruiker_id: int
    naar_gebruiker_id: Optional[int]    # None = algemene melding
    planning_datum: Optional[str]       # ISO format: "YYYY-MM-DD"
    bericht: str
    is_gelezen: bool
    prioriteit: str                     # 'laag', 'normaal', 'hoog'
    aangemaakt_op: Optional[str]
    gelezen_op: Optional[str]
```

#### Database Mapping

| Attribuut | Database Veld | Type | Opmerking |
|-----------|--------------|------|-----------|
| `id` | `notities.id` | INTEGER | Primary key |
| `van_gebruiker_id` | `notities.van_gebruiker_id` | INTEGER | FK naar gebruikers (verzender) |
| `naar_gebruiker_id` | `notities.naar_gebruiker_id` | INTEGER | FK naar gebruikers (ontvanger), nullable |
| `planning_datum` | `notities.planning_datum` | TEXT | Nullable |
| `bericht` | `notities.bericht` | TEXT | Max 5000 chars |
| `is_gelezen` | `notities.is_gelezen` | BOOLEAN | Default 0 |
| `prioriteit` | `notities.prioriteit` | TEXT | 'laag', 'normaal', 'hoog' |
| `aangemaakt_op` | `notities.aangemaakt_op` | TEXT | ISO timestamp |
| `gelezen_op` | `notities.gelezen_op` | TEXT | ISO timestamp |

#### Factory Method

```python
notitie = Notitie.van_database_row(row)
```

#### Conversie naar Database

```python
data = notitie.naar_database_dict()
# => {'van_gebruiker_id': 1, 'naar_gebruiker_id': 2, ...}
```

#### Validatie Functies

```python
# Valideer notitie data
is_geldig, fout = valideer_notitie(
    van_gebruiker_id=1,
    bericht="Belangrijke melding",
    prioriteit="hoog",
    naar_gebruiker_id=2
)
# => (True, None)

# Valideer prioriteit
is_geldig, fout = valideer_prioriteit("hoog")
# => (True, None)
```

---

## HR-Regelvalidatie

### `HRConfig` (hr_regel_domein.py)

**Gebruik:** Container voor HR configuratie parameters (drempelwaarden, shift metadata).

```python
@dataclass
class HRConfig:
    regels: Dict[str, Any] = field(default_factory=dict)
    shift_tijden: Dict[str, Any] = field(default_factory=dict)
    rode_lijn_start: date = date(2026, 1, 1)
    rode_lijn_interval: int = 28
```

#### Structuur `regels`

```python
{
    "MAX_DAGEN_RIJ": {
        "waarde": 7,
        "eenheid": "dagen",
        "ernst_niveau": "WARNING",
        "beschrijving": "Maximaal aantal dagen op rij"
    },
    "MIN_RUSTTIJD": {
        "waarde": 11,
        "eenheid": "uren",
        "ernst_niveau": "CRITICAL",
        "beschrijving": "Minimale rusttijd tussen shifts"
    },
    # ... 5 andere regels
}
```

#### Structuur `shift_tijden`

```python
{
    "D": {
        "start_tijd": time(6, 0),
        "eind_tijd": time(14, 0),
        "is_nachtshift": False,
        "is_rustdag": False,
        "telt_als_werkdag": True,
        "uren_per_shift": 8.0
    },
    "N": {
        "start_tijd": time(22, 0),
        "eind_tijd": time(6, 0),
        "is_nachtshift": True,  # Eindigt volgende dag!
        # ...
    }
}
```

#### Methods

```python
config = HRConfig(regels={...}, shift_tijden={...})

# Haal regelwaarde op
waarde = config.get_regel_waarde("MAX_DAGEN_RIJ", default=7)
# => 7

# Haal ernst niveau op
ernst = config.get_regel_ernst("MIN_RUSTTIJD", default="WARNING")
# => "CRITICAL"

# Haal shift metadata op
metadata = config.get_shift_metadata("D")
# => {'start_tijd': time(6, 0), 'eind_tijd': time(14, 0), ...}
```

---

### `PlanningShift` (HR versie - hr_regel_domein.py)

**⚠️ LET OP:** Dit is een **andere** PlanningShift dan in `planning_domein.py`! Deze variant is specifiek voor HR-validatie met extra metadata.

**🔴 VERSCHIL:** Deze HR-versie gebruikt `shiftcode` (ZONDER underscore), terwijl planning_domein.py `shift_code` (MET underscore) gebruikt. Controleer welke variant je importeert!

```python
@dataclass
class PlanningShift:
    id: int
    planning_id: int
    medewerker_id: int
    datum: date                         # Python date object (niet string!)
    shiftcode: str                      # ❌ ZONDER underscore (HR-versie)
    start_tijd: Optional[time] = None   # Python time object
    eind_tijd: Optional[time] = None
    is_nachtshift: bool = False
    is_rustdag: bool = False
    rustdag_type: Optional[str] = None  # "RXW", "RXF", "CXW", "CXA"
    telt_als_werkdag: bool = True
    uren_per_shift: Optional[float] = None
```

#### Database Mapping

| Attribuut | Database Veld | Type | Opmerking |
|-----------|--------------|------|-----------|
| `id` | `planning.id` | INTEGER | Primary key |
| `planning_id` | `planning.id` | INTEGER | Altijd 1 in huidige impl |
| `medewerker_id` | `planning.gebruiker_id` | INTEGER | FK naar gebruikers |
| `datum` | `planning.datum` | TEXT | Parsed naar Python `date` |
| `shiftcode` | `planning.shift_code` | TEXT | - |
| `start_tijd` | `shift_tijden.start_tijd` | TEXT | Parsed naar Python `time` |
| `eind_tijd` | `shift_tijden.eind_tijd` | TEXT | Parsed naar Python `time` |
| `is_nachtshift` | `shift_tijden.is_nachtshift` | BOOLEAN | Van metadata |
| `is_rustdag` | `shift_tijden.is_rustdag` | BOOLEAN | Van metadata |
| `rustdag_type` | `shift_tijden.rustdag_type` | TEXT | Van metadata |
| `telt_als_werkdag` | `shift_tijden.telt_als_werkdag` | BOOLEAN | Van metadata |
| `uren_per_shift` | `shift_tijden.uren_per_shift` | REAL | Van metadata |

#### Factory Method

```python
shift = PlanningShift.van_database_row(row, shift_metadata=metadata)
```

**KRITIEK:** Deze factory accepteert TWEE parameters:
1. `row`: Planning data uit `planning` tabel
2. `shift_metadata`: Shift data uit `shift_tijden` tabel (optioneel)

---

### `RegelOvertreding` (hr_regel_domein.py)

**Gebruik:** Enkelvoudige HR-regelovertreding met volledige context.

```python
@dataclass
class RegelOvertreding:
    regel_code: str                     # "MAX_DAGEN_RIJ", "MIN_RUSTTIJD"
    regel_naam: str                     # "Maximaal Dagen Op Rij"
    medewerker_id: int
    datum: date                         # Primaire datum
    datum_tot: Optional[date]           # Voor periode-regels
    bericht: str                        # "Slechts 9u rust tussen diensten"
    ernst: str                          # "INFO", "WARNING", "CRITICAL"
    betrokken_shifts: List[int] = field(default_factory=list)  # Shift IDs
```

#### Ernst Niveaus

| Ernst | Kleur | Betekenis | Voorbeeld |
|-------|-------|-----------|-----------|
| `INFO` | Blauw | Informatief, geen overtreding | "Weekend gewerkt" |
| `WARNING` | Oranje | Waarschuwing, liefst vermijden | "6 dagen op rij" |
| `CRITICAL` | Rood | Kritieke overtreding, override nodig | "Slechts 8u rust" |

#### Method: `__str__()`

```python
overtreding = RegelOvertreding(
    regel_code="MIN_RUSTTIJD",
    regel_naam="Minimale Rusttijd",
    medewerker_id=1,
    datum=date(2026, 1, 15),
    datum_tot=date(2026, 1, 16),
    bericht="Slechts 9u rust tussen diensten",
    ernst="CRITICAL"
)

print(overtreding)
# => "[CRITICAL] Minimale Rusttijd op 2026-01-15 t/m 2026-01-16: Slechts 9u rust tussen diensten"
```

---

### `ValidatieRapport` (hr_regel_domein.py)

**Gebruik:** Collectie van overtredingen voor een planning of shift.

```python
@dataclass
class ValidatieRapport:
    overtredingen: List[RegelOvertreding] = field(default_factory=list)
    is_geldig: bool = True  # False als CRITICAL overtredingen aanwezig
```

#### Methods

```python
rapport = ValidatieRapport()

# Voeg overtreding toe
rapport.voeg_toe(overtreding)

# Voeg meerdere toe
rapport.voeg_toe_bulk([overtreding1, overtreding2, ...])

# Filter voor medewerker
overtredingen = rapport.filter_voor_medewerker(medewerker_id=1)
# => [RegelOvertreding, ...]

# Filter voor datum
overtredingen = rapport.filter_voor_datum(datum=date(2026, 1, 15))
# => [RegelOvertreding, ...]

# Filter op ernst
critical = rapport.filter_op_ernst("CRITICAL")
warning = rapport.filter_op_ernst("WARNING")
info = rapport.filter_op_ernst("INFO")

# Check CRITICAL aanwezig
heeft_critical = rapport.heeft_critical_overtredingen()
# => True/False

# Totaal aantal
totaal = rapport.aantal_overtredingen()
# => 5

# String representatie
print(rapport)
# => "ValidatieRapport: 5 overtredingen (CRITICAL: 1, WARNING: 3, INFO: 1)"
```

---

### `AbstractRegelValidator` (hr_regel_domein.py)

**Gebruik:** Abstracte basis klasse voor alle regel validators (Strategy Pattern).

```python
class AbstractRegelValidator(ABC):
    @abstractmethod
    def valideer(
        self,
        shifts: List[PlanningShift],
        config: HRConfig
    ) -> List[RegelOvertreding]:
        """Valideer shifts tegen deze regel."""
        pass
```

#### Helper Methods (voor subclasses)

```python
class MijnValidator(AbstractRegelValidator):
    def valideer(self, shifts, config):
        # Groepeer per medewerker
        per_medewerker = self._groepeer_per_medewerker(shifts)
        # => {1: [shift1, shift2], 2: [shift3, shift4]}

        # Sorteer op datum
        gesorteerd = self._sorteer_op_datum(shifts)
        # => [shift_dag1, shift_dag2, shift_dag3]
```

#### Implementaties

Er zijn 7 concrete validators in `src/services/domein/validators/`:
1. `RodeLijnValidator` - 28-dag cyclus met max werkdagen
2. `MaxDagenOpRijValidator` - Max consecutieve werkdagen
3. `MaxUrenPerWeekValidator` - Max uren per kalenderweek
4. `MinRusttijdValidator` - Min rusttijd tussen shifts (midnight crossing)
5. `NachtshiftOpvolgingValidator` - Na nacht moet late shift
6. `MaxWeekendsOpRijValidator` - Max weekends op rij (vr 22:00 - ma 06:00)
7. `RXGapValidator` - Max dagen tussen RX* rustdagen (segment breaking)

---

## Validatie Functies

### Pattern

Alle validatie functies retourneren `Tuple[bool, Optional[str]]`:

```python
is_geldig, foutmelding = valideer_functie(...)

if not is_geldig:
    print(f"Fout: {foutmelding}")
    # => "Fout: Gebruikersnaam moet minimaal 3 karakters bevatten"
```

### Overzicht

| Module | Functie | Valideert |
|--------|---------|-----------|
| `gebruiker_domein.py` | `valideer_gebruiker_data()` | Gebruikersnaam, naam, rol |
| `gebruiker_domein.py` | `valideer_startweek_typedienst()` | Startweek (1-6) |
| `gebruiker_domein.py` | `mag_gebruiker_deactiveren()` | Deactivatie rechten |
| `rol_domein.py` | `valideer_rol()` | Rol code |
| `post_domein.py` | `valideer_post_data()` | Post naam, beschrijving |
| `competentie_domein.py` | `valideer_competentie_data()` | Competentie naam, beschrijving |
| `shiftcode_domein.py` | `valideer_shiftcode_data()` | Shiftcode, tijden |
| `planning_domein.py` | `valideer_planning_shift()` | Shift data |
| `planning_domein.py` | `valideer_planning_status()` | Status ('concept', 'gepubliceerd') |
| `verlof_domein.py` | `valideer_verlof_aanvraag()` | Verlofaanvraag data |
| `verlof_domein.py` | `valideer_verlof_status()` | Status ('pending', 'goedgekeurd', 'geweigerd') |
| `notitie_domein.py` | `valideer_notitie()` | Notitie data |
| `notitie_domein.py` | `valideer_prioriteit()` | Prioriteit ('laag', 'normaal', 'hoog') |

---

## Common Patterns

### 1. Factory Pattern

**Altijd gebruiken** voor conversie van database rows naar domein objecten:

```python
# Repo retourneert Dict
row = GebruikerRepo.haal_gebruiker(gebruiker_id=1)

# Domein laag doet object mapping
gebruiker = Gebruiker.van_database_row(row)
```

### 2. Validatie Voor Save

**Service laag** moet valideren voor database operaties:

```python
# In applicatie service
def maak_gebruiker(gebruikersnaam: str, voornaam: str, ...) -> int:
    # Valideer eerst
    is_geldig, fout = valideer_gebruiker_data(gebruikersnaam, ...)
    if not is_geldig:
        raise ValueError(fout)

    # Dan pas save
    return GebruikerRepo.maak_gebruiker(...)
```

### 3. Type Conversie

**Database types → Python types:**

```python
# String naar date
datum_str = "2026-01-15"
datum_obj = date.fromisoformat(datum_str)

# String naar time
tijd_str = "06:00:00"
tijd_obj = datetime.strptime(tijd_str, '%H:%M:%S').time()

# Boolean (SQLite integer)
is_actief_int = 1
is_actief_bool = bool(is_actief_int)
```

### 4. Optional Fields

**Nullable database velden → Optional type hints:**

```python
@dataclass
class Object:
    verplicht_veld: str                # NOT NULL
    optioneel_veld: Optional[str]      # NULL mogelijk
```

**Gebruik `row.get()` voor nullable velden:**

```python
@classmethod
def van_database_row(cls, row):
    return cls(
        verplicht=row['verplicht'],           # KeyError als niet aanwezig
        optioneel=row.get('optioneel')        # None als niet aanwezig
    )
```

### 5. Naar Database Conversie

**Exclude auto-generated fields:**

```python
def naar_database_dict(self) -> Dict[str, Any]:
    return {
        'gebruiker_id': self.gebruiker_id,
        'datum': self.datum,
        # GEEN 'id' (auto-increment)
        # GEEN 'aangemaakt_op' (DEFAULT CURRENT_TIMESTAMP)
    }
```

### 6. Soft Delete Pattern

**is_actief boolean i.p.v. DELETE:**

```python
@dataclass
class Object:
    is_actief: bool
    gedeactiveerd_op: Optional[str]

# In repo/service
def deactiveer_object(object_id: int):
    Repo.update_object(
        object_id,
        is_actief=False,
        gedeactiveerd_on=datetime.now().isoformat()
    )
```

### 7. Hiërarchische Toegang (Rollen)

**Hoger niveau = toegang tot lager:**

```python
if huidige_rol.niveau >= vereiste_rol.niveau:
    # Toegang verleend
```

### 8. List Comprehensions

**Filter domein objecten:**

```python
# Alleen actieve objecten
actieve = [obj for obj in objecten if obj.is_actief]

# Filter op datum
vandaag = [shift for shift in shifts if shift.datum == date.today()]

# Map naar IDs
ids = [obj.id for obj in objecten]
```

---

## Zie Ook

- [Database Schema Referentie](./database_schema.md) - Database structuur en velden
- [Services API Referentie](./services_api.md) - Service laag methodes
- [GUI Components Referentie](./gui_components.md) - UI widgets en schermen
- [Configuratie Referentie](./configuratie.md) - Systeem configuratie

---

**Einde Domein Objecten Referentie**
