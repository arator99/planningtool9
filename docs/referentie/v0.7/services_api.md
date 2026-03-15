# Services API Referentie

**Versie:** 0.7.x
**Laatst bijgewerkt:** 2026-03-11
**Doel:** Complete referentie van alle service methodes (Repo + Applicatie lagen)

---

## 📋 Inhoudsopgave

1. [Introductie](#introductie)
2. [Architectuur Overzicht](#architectuur-overzicht)
3. [Gebruikers Services](#gebruikers-services)
4. [Authenticatie Services](#authenticatie-services)
5. [Rollen Services](#rollen-services)
6. [Referentiedata Services](#referentiedata-services)
7. [Planning Services](#planning-services)
8. [Verlof Services](#verlof-services)
9. [Notities Services](#notities-services)
10. [HR-Validatie Services](#hr-validatie-services) → Zie ook [hr_validatie.md](./hr_validatie.md)
11. [Scherm Rechten Services](#scherm-rechten-services)
12. [Auto-Scheduling Services](#auto-scheduling-services)
13. [Rapport Services](#rapport-services)
14. [Common Patterns](#common-patterns)

### Nieuwe Services (sinds 2026-01-16)

| Service | Locatie | Doel |
|---------|---------|------|
| VerlofSaldoService | `applicatie/verlof_saldo_service.py` | FIFO verlof berekening, jaar overdracht |
| AutoSchedulingService | `applicatie/auto_scheduling_service.py` | Automatische shift toewijzing |
| KandidaatScoringService | `applicatie/kandidaat_scoring_service.py` | Kandidaat scoring voor suggesties |
| SuggestieService | `applicatie/suggestie_service.py` | Shift suggesties |
| BalansService | `applicatie/balans_service.py` | Uren/verlof balans berekening |
| TShiftBudgetService | `applicatie/t_shift_budget_service.py` | T-shift budget beheer |
| RodeLijnService | `applicatie/rode_lijn_service.py` | Rode lijn periodes en status |
| ContractStatusService | `applicatie/contract_status_service.py` | Contract status per gebruiker |
| BatchCompleetService | `applicatie/batch_compleet_service.py` | Batch operaties |
| BackupService | `applicatie/backup_service.py` | Database backup/restore |
| RapportExcelExport | `applicatie/rapport_excel_export.py` | Excel export voor rapporten |

---

## Introductie

### Wat zijn Services?

Services vormen de **business logic laag** van de applicatie, verdeeld in 2 sub-lagen:

1. **Repo (Repository)** - Pure SQL data access, retourneert `Dict[str, Any]`
2. **Applicatie** - Orchestratie, gebruikt domein objecten, coordineert tussen repo en GUI

### Architectuur Flow

```
GUI → Applicatie Service → Domein Logic → Repo (SQL)
                    ↓                         ↓
              Domain Objects            Dict[str, Any]
```

### Locaties

- **Repo:** `src/services/repo/` - SQL queries
- **Applicatie:** `src/services/applicatie/` - Orchestratie
- **Domein:** `src/services/domein/` - Business rules (zie [domein_objecten.md](./domein_objecten.md))

---

## Architectuur Overzicht

### Repo Laag Principes

**MOET:**
- Retourneer altijd `Dict[str, Any]` of `List[Dict[str, Any]]`
- Pure SQL queries zonder business logica
- Gebruik `with get_db() as conn:` context manager
- Log fouten met `logger.error(..., exc_info=True)`

**MAG NIET:**
- Domein objecten kennen of importeren
- Business rules implementeren
- Exceptions afhandelen (laat ze door naar applicatie laag)

### Applicatie Laag Principes

**MOET:**
- Valideer input met domein validatie functies
- Map Dict naar domein objecten via `van_database_row()`
- Orchestreer tussen repo en domein
- Raise betekenisvolle exceptions voor GUI

**MAG NIET:**
- SQL queries schrijven (gebruik repo)
- Business rules dupliceren (gebruik domein functies)

---

## Gebruikers Services

### GebruikerRepo

**Locatie:** `src/services/repo/gebruiker_repo.py`

#### `vind_gebruiker_op_gebruikersnaam()`

```python
@staticmethod
def vind_gebruiker_op_gebruikersnaam(gebruikersnaam: str) -> Optional[Dict[str, Any]]
```

**Doel:** Haal gebruiker op voor login (inclusief wachtwoord hash).

**Parameters:**
- `gebruikersnaam` (str): Gebruikersnaam om te zoeken

**Returns:**
- `Dict` met velden: `id`, `gebruiker_uuid`, `gebruikersnaam`, `wachtwoord_hash`, `volledige_naam`, `voornaam`, `achternaam`, `rol`, `is_actief`
- `None` als niet gevonden

**SQL Query:**
```sql
SELECT id, gebruiker_uuid, gebruikersnaam, wachtwoord_hash,
       volledige_naam, voornaam, achternaam, rol, is_actief
FROM gebruikers
WHERE gebruikersnaam = ? AND is_actief = 1
```

**Gebruik:**
```python
from src.services.repo.gebruiker_repo import GebruikerRepo

row = GebruikerRepo.vind_gebruiker_op_gebruikersnaam("jan.peeters")
# => {'id': 1, 'gebruikersnaam': 'jan.peeters', ...}
```

---

#### `update_laatste_login()`

```python
@staticmethod
def update_laatste_login(gebruiker_id: int) -> None
```

**Doel:** Update timestamp laatste login.

**Parameters:**
- `gebruiker_id` (int): ID van de gebruiker

**SQL Query:**
```sql
UPDATE gebruikers
SET laatste_login = CURRENT_TIMESTAMP
WHERE id = ?
```

---

#### `haal_gebruiker_op_id()`

```python
@staticmethod
def haal_gebruiker_op_id(gebruiker_id: int) -> Optional[Dict[str, Any]]
```

**Doel:** Haal volledige gebruiker data op basis van ID.

**Parameters:**
- `gebruiker_id` (int): ID van de gebruiker

**Returns:**
- `Dict` met ALLE gebruiker velden (incl. `is_reserve`, `startweek_typedienst`, `theme_voorkeur`, etc.)
- `None` als niet gevonden

**SQL Query:**
```sql
SELECT id, gebruiker_uuid, gebruikersnaam, volledige_naam,
       voornaam, achternaam, rol, is_actief, is_reserve,
       startweek_typedienst, shift_voorkeuren, theme_voorkeur,
       aangemaakt_op, gedeactiveerd_op, laatste_login
FROM gebruikers
WHERE id = ?
```

---

#### `haal_alle_gebruikers()`

```python
@staticmethod
def haal_alle_gebruikers() -> List[Dict[str, Any]]
```

**Doel:** Haal alle gebruikers op (actief + inactief).

**Returns:** Lijst met Dict objecten

**SQL Query:**
```sql
SELECT [alle velden]
FROM gebruikers
ORDER BY volledige_naam
```

---

#### `haal_actieve_gebruikers()`

```python
@staticmethod
def haal_actieve_gebruikers() -> List[Dict[str, Any]]
```

**Doel:** Haal alleen actieve gebruikers op.

**Returns:** Lijst met Dict objecten

**SQL Query:**
```sql
SELECT [alle velden]
FROM gebruikers
WHERE is_actief = 1
ORDER BY volledige_naam
```

---

#### `maak_gebruiker()`

```python
@staticmethod
def maak_gebruiker(
    gebruiker_uuid: str,
    gebruikersnaam: str,
    wachtwoord_hash: str,
    volledige_naam: str,
    voornaam: str,
    achternaam: str,
    rol: str,
    is_reserve: bool = False,
    startweek_typedienst: Optional[int] = None,
    shift_voorkeuren: Optional[str] = None,
    theme_voorkeur: str = 'light'
) -> int
```

**Doel:** Creëer nieuwe gebruiker in database.

**Parameters:** Alle gebruiker velden (zie domein object)

**Returns:** `int` - ID van nieuwe gebruiker

**SQL Query:**
```sql
INSERT INTO gebruikers (gebruiker_uuid, gebruikersnaam, wachtwoord_hash, ...)
VALUES (?, ?, ?, ...)
```

---

#### `update_gebruiker()`

```python
@staticmethod
def update_gebruiker(
    gebruiker_id: int,
    voornaam: str,
    achternaam: str,
    volledige_naam: str,
    rol: str,
    is_reserve: bool,
    startweek_typedienst: Optional[int],
    shift_voorkeuren: Optional[str],
    theme_voorkeur: str
) -> None
```

**Doel:** Update bestaande gebruiker.

**Parameters:** Gebruiker ID + te updaten velden

**SQL Query:**
```sql
UPDATE gebruikers
SET voornaam = ?, achternaam = ?, volledige_naam = ?, ...
WHERE id = ?
```

---

#### `deactiveer_gebruiker()`

```python
@staticmethod
def deactiveer_gebruiker(gebruiker_id: int) -> None
```

**Doel:** Soft delete gebruiker (is_actief = 0).

**SQL Query:**
```sql
UPDATE gebruikers
SET is_actief = 0, gedeactiveerd_op = CURRENT_TIMESTAMP
WHERE id = ?
```

---

#### `activeer_gebruiker()`

```python
@staticmethod
def activeer_gebruiker(gebruiker_id: int) -> None
```

**Doel:** Heractiveer gebruiker.

**SQL Query:**
```sql
UPDATE gebruikers
SET is_actief = 1, gedeactiveerd_op = NULL
WHERE id = ?
```

---

### GebruikerService

**Locatie:** `src/services/applicatie/gebruiker_service.py`

#### `haal_alle_gebruikers()`

```python
@staticmethod
def haal_alle_gebruikers(alleen_actief: bool = False) -> List[GebruikerVolledig]
```

**Doel:** Haal gebruikers op, gemapped naar domein objecten.

**Parameters:**
- `alleen_actief` (bool): Filter op actieve status

**Returns:** `List[GebruikerVolledig]` - Domein objecten

**Flow:**
```python
# 1. Haal ruwe data via repo
rows = GebruikerRepo.haal_actieve_gebruikers() if alleen_actief else GebruikerRepo.haal_alle_gebruikers()

# 2. Map naar domein objecten
gebruikers = [GebruikerVolledig.van_database_row_volledig(row) for row in rows]

# 3. Return domein objecten
return gebruikers
```

**Gebruik:**
```python
from src.services.applicatie.gebruiker_service import GebruikerService

gebruikers = GebruikerService.haal_alle_gebruikers(alleen_actief=True)
for gebruiker in gebruikers:
    print(f"{gebruiker.volledige_naam} - {gebruiker.rol}")
```

---

#### `haal_gebruiker()`

```python
@staticmethod
def haal_gebruiker(gebruiker_id: int) -> Optional[GebruikerVolledig]
```

**Doel:** Haal specifieke gebruiker op.

**Returns:** `GebruikerVolledig` of `None`

---

#### `maak_gebruiker()`

```python
@staticmethod
def maak_gebruiker(
    gebruikersnaam: str,
    wachtwoord: str,
    voornaam: str,
    achternaam: str,
    rol: str,
    is_reserve: bool = False,
    startweek_typedienst: Optional[int] = None,
    shift_voorkeuren: Optional[str] = None,
    theme_voorkeur: str = 'light'
) -> int
```

**Doel:** Creëer nieuwe gebruiker met validatie.

**Flow:**
```python
# 1. Genereer volledige naam (Belgisch formaat)
volledige_naam = gebruiker_domein.genereer_volledige_naam(voornaam, achternaam)

# 2. Valideer gebruiker data
is_geldig, fout = gebruiker_domein.valideer_gebruiker_data(
    gebruikersnaam, volledige_naam, voornaam, achternaam, rol
)
if not is_geldig:
    raise ValueError(fout)

# 3. Valideer startweek (indien opgegeven)
if startweek_typedienst:
    is_geldig, fout = gebruiker_domein.valideer_startweek_typedienst(startweek_typedienst)
    if not is_geldig:
        raise ValueError(fout)

# 4. Hash wachtwoord
wachtwoord_hash = authenticatie_domein.hash_wachtwoord(wachtwoord)

# 5. Genereer UUID
gebruiker_uuid = str(uuid.uuid4())

# 6. Sla op via repo
return GebruikerRepo.maak_gebruiker(
    gebruiker_uuid, gebruikersnaam, wachtwoord_hash,
    volledige_naam, voornaam, achternaam, rol,
    is_reserve, startweek_typedienst, shift_voorkeuren, theme_voorkeur
)
```

**Raises:**
- `ValueError`: Bij validatie fouten
- `Exception`: Bij database fouten

---

#### `update_gebruiker()`

```python
@staticmethod
def update_gebruiker(
    gebruiker_id: int,
    voornaam: str,
    achternaam: str,
    rol: str,
    is_reserve: bool,
    startweek_typedienst: Optional[int] = None,
    shift_voorkeuren: Optional[str] = None,
    theme_voorkeur: str = 'light'
) -> None
```

**Doel:** Update gebruiker met validatie.

**Flow:** Valideer → Genereer volledige naam → Update via repo

**Raises:**
- `ValueError`: Bij validatie fouten

---

#### `deactiveer_gebruiker()`

```python
@staticmethod
def deactiveer_gebruiker(gebruiker_id: int, huidige_gebruiker_id: int) -> None
```

**Doel:** Deactiveer gebruiker met business rule check.

**Flow:**
```python
# 1. Check of deactivatie toegestaan is (mag niet jezelf deactiveren)
mag_deactiveren, fout = gebruiker_domein.mag_gebruiker_deactiveren(
    gebruiker_id, huidige_gebruiker_id
)
if not mag_deactiveren:
    raise ValueError(fout)

# 2. Deactiveer via repo
GebruikerRepo.deactiveer_gebruiker(gebruiker_id)
```

---

#### `activeer_gebruiker()`

```python
@staticmethod
def activeer_gebruiker(gebruiker_id: int) -> None
```

**Doel:** Heractiveer gebruiker.

---

#### `reset_wachtwoord()`

```python
@staticmethod
def reset_wachtwoord(gebruiker_id: int, nieuw_wachtwoord: str) -> None
```

**Doel:** Reset wachtwoord met validatie.

**Flow:**
```python
# 1. Valideer wachtwoord sterkte
is_geldig, fout = authenticatie_domein.valideer_wachtwoord_sterkte(nieuw_wachtwoord)
if not is_geldig:
    raise ValueError(fout)

# 2. Hash nieuw wachtwoord
wachtwoord_hash = authenticatie_domein.hash_wachtwoord(nieuw_wachtwoord)

# 3. Update via repo
GebruikerRepo.update_wachtwoord(gebruiker_id, wachtwoord_hash)
```

---

## Authenticatie Services

### AuthenticatieService

**Locatie:** `src/services/applicatie/authenticatie_service.py`

#### `login()`

```python
@staticmethod
def login(gebruikersnaam: str, wachtwoord: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]
```

**Doel:** Authenticeer gebruiker en start sessie.

**Parameters:**
- `gebruikersnaam` (str): Gebruikersnaam
- `wachtwoord` (str): Plain text wachtwoord

**Returns:**
- `Tuple[bool, Optional[str], Optional[Dict]]`
  - `(True, None, sessie_data)` bij succes
  - `(False, "foutmelding", None)` bij falen

**Flow:**
```python
# 1. Haal gebruiker op via repo
row = GebruikerRepo.vind_gebruiker_op_gebruikersnaam(gebruikersnaam)
if not row:
    return (False, "Ongeldige inloggegevens", None)

# 2. Verifieer wachtwoord (domein logica)
wachtwoord_hash = row['wachtwoord_hash']
if not authenticatie_domein.verifieer_wachtwoord(wachtwoord, wachtwoord_hash):
    return (False, "Ongeldige inloggegevens", None)

# 3. Map naar domein object
gebruiker = Gebruiker.van_database_row(row)

# 4. Update laatste login via repo
GebruikerRepo.update_laatste_login(gebruiker.id)

# 5. Start sessie
sessie_data = gebruiker.naar_sessie_data()
Sessie.start(sessie_data)

return (True, None, sessie_data)
```

**Gebruik:**
```python
from src.services.applicatie.authenticatie_service import AuthenticatieService

succes, fout, sessie_data = AuthenticatieService.login("jan.peeters", "wachtwoord123")
if succes:
    print(f"Welkom {sessie_data['volledige_naam']}!")
else:
    print(f"Login mislukt: {fout}")
```

---

#### `logout()`

```python
@staticmethod
def logout() -> None
```

**Doel:** Beëindig huidige sessie.

**Flow:**
```python
Sessie.stop()
```

---

## Rollen Services

### RolService

**Locatie:** `src/services/applicatie/rol_service.py`

#### `haal_alle_rollen()`

```python
@staticmethod
def haal_alle_rollen() -> List[Rol]
```

**Doel:** Haal alle rol definities op (pure domein, GEEN database).

**Returns:** `List[Rol]` - 4 rollen (teamlid, planner, beheerder, admin)

**Gebruik:**
```python
from src.services.applicatie.rol_service import RolService

rollen = RolService.haal_alle_rollen()
for rol in rollen:
    print(f"{rol.naam} (niveau {rol.niveau})")
```

---

#### `haal_rol()`

```python
@staticmethod
def haal_rol(rol_code: str) -> Optional[Rol]
```

**Doel:** Haal specifieke rol op.

**Returns:** `Rol` of `None`

---

#### `is_geldige_rol()`

```python
@staticmethod
def is_geldige_rol(rol_code: str) -> bool
```

**Doel:** Check of rol code geldig is.

---

#### `haal_toegestane_rollen_voor_gebruiker()`

```python
@staticmethod
def haal_toegestane_rollen_voor_gebruiker(gebruiker_rol: str) -> List[Rol]
```

**Doel:** Haal rollen waar gebruiker toegang toe heeft (eigen niveau + lager).

**Gebruik:**
```python
# Admin kan alle rollen zien
toegestaan = RolService.haal_toegestane_rollen_voor_gebruiker('admin')
# => [Rol(teamlid), Rol(planner), Rol(beheerder), Rol(admin)]

# Planner kan alleen teamlid en planner zien
toegestaan = RolService.haal_toegestane_rollen_voor_gebruiker('planner')
# => [Rol(teamlid), Rol(planner)]
```

---

## Referentiedata Services

### PostRepo

**Locatie:** `src/services/repo/post_repo.py`

#### `haal_alle_posten()`

```python
@staticmethod
def haal_alle_posten() -> List[Dict[str, Any]]
```

**Returns:** Lijst met alle werkposten

**SQL:**
```sql
SELECT id, naam, beschrijving, telt_als_werkdag, reset_12u_rust,
       breekt_werk_reeks, is_actief, aangemaakt_op, gedeactiveerd_op
FROM werkposten
ORDER BY naam
```

---

#### `maak_post()`

```python
@staticmethod
def maak_post(
    naam: str,
    beschrijving: Optional[str],
    telt_als_werkdag: bool,
    reset_12u_rust: bool,
    breekt_werk_reeks: bool
) -> int
```

**Returns:** ID van nieuwe post

---

### PostService

**Locatie:** `src/services/applicatie/post_service.py`

#### `haal_alle_posten()`

```python
@staticmethod
def haal_alle_posten(alleen_actief: bool = False) -> List[Post]
```

**Returns:** `List[Post]` - Domein objecten

---

#### `maak_post()`

```python
@staticmethod
def maak_post(
    naam: str,
    beschrijving: Optional[str] = None,
    telt_als_werkdag: bool = True,
    reset_12u_rust: bool = False,
    breekt_werk_reeks: bool = False
) -> int
```

**Flow:** Valideer → Normaliseer naam → Sla op

**Raises:** `ValueError` bij validatie fouten

---

### CompetentieRepo / CompetentieService

**Zelfde pattern als PostRepo/PostService:**
- `haal_alle_competenties()`
- `maak_competentie(naam, beschrijving, categorie)`
- `update_competentie()`
- `deactiveer_competentie()`

---

### ShiftcodeRepo / ShiftcodeService

**Locatie:** `src/services/repo/shiftcode_repo.py` + `src/services/applicatie/shiftcode_service.py`

#### `haal_alle_shiftcodes()` (Service)

```python
@staticmethod
def haal_alle_shiftcodes() -> List[Shiftcode]
```

**Returns:** `List[Shiftcode]` - Domein objecten

**KRITIEK:** Gebruik correcte veldnamen:
- `shift.shift_type` (NIET `beschrijving`)
- `shift.start_uur` (NIET `start_tijd`)
- `shift.eind_uur` (NIET `eind_tijd`)
- `shift.is_kritisch` (NIET `is_actief`)

---

#### `maak_shiftcode()` (Service)

```python
@staticmethod
def maak_shiftcode(
    code: str,
    werkpost_id: Optional[int],
    dag_type: Optional[str],
    shift_type: Optional[str],
    start_uur: Optional[str],
    eind_uur: Optional[str],
    is_kritisch: bool = False
) -> int
```

**Flow:** Valideer code + tijden → Normaliseer code (uppercase) → Sla op

---

## Planning Services

### PlanningRepo

**Locatie:** `src/services/repo/planning_repo.py`

#### `haal_maand_planning()`

```python
@staticmethod
def haal_maand_planning(jaar: int, maand: int) -> List[Dict[str, Any]]
```

**Doel:** Haal alle planning shifts voor een specifieke maand.

**Parameters:**
- `jaar` (int): Jaar (bijv. 2026)
- `maand` (int): Maand (1-12)

**Returns:** Lijst met Dict objecten

**SQL:**
```sql
SELECT id, gebruiker_id, datum, shift_code, notitie,
       notitie_gelezen, status, aangemaakt_op
FROM planning
WHERE datum >= ? AND datum < ?
ORDER BY datum, gebruiker_id
```

---

#### `sla_shift_op()`

```python
@staticmethod
def sla_shift_op(
    gebruiker_id: int,
    datum: str,
    shift_code: Optional[str],
    status: str = 'concept'
) -> int
```

**Doel:** Sla shift op (UPSERT - insert or update).

**SQL:**
```sql
INSERT INTO planning (gebruiker_id, datum, shift_code, status)
VALUES (?, ?, ?, ?)
ON CONFLICT(gebruiker_id, datum)
DO UPDATE SET shift_code = ?, status = ?
```

---

#### `haal_maand_shifts_bulk()` (voor HR-validatie)

```python
@staticmethod
def haal_maand_shifts_bulk(jaar: int, maand: int) -> List[Dict[str, Any]]
```

**Doel:** Haal shifts MET shift metadata (JOIN met shift_tijden).

**Returns:** Dict met extra velden: `start_tijd`, `eind_tijd`, `is_nachtshift`, etc.

---

### PlanningService

**Locatie:** `src/services/applicatie/planning_service.py`

#### `haal_maand_planning()`

```python
@staticmethod
def haal_maand_planning(jaar: int, maand: int) -> MaandPlanning
```

**Doel:** Haal maandplanning als domein aggregaat.

**Returns:** `MaandPlanning` object met shifts lijst

**Flow:**
```python
# 1. Haal ruwe data via repo
rows = PlanningRepo.haal_maand_planning(jaar, maand)

# 2. Map naar domein objecten
shifts = [PlanningShift.van_database_row(row) for row in rows]

# 3. Creëer aggregaat
return MaandPlanning(jaar=jaar, maand=maand, shifts=shifts)
```

---

#### `sla_shift_op()`

```python
@staticmethod
def sla_shift_op(
    gebruiker_id: int,
    datum: str,
    shift_code: Optional[str],
    status: str = 'concept'
) -> int
```

**Flow:** Valideer datum + status → Sla op via repo

**Raises:** `ValueError` bij validatie fouten

---

#### `sla_planning_op_bulk()`

```python
@staticmethod
def sla_planning_op_bulk(shifts: List[PlanningShift]) -> None
```

**Doel:** Sla meerdere shifts tegelijk op (transactie).

**Flow:**
```python
# 1. Valideer alle shifts
for shift in shifts:
    is_geldig, fout = valideer_planning_shift(...)
    if not is_geldig:
        raise ValueError(fout)

# 2. Start transactie
with get_db() as conn:
    cursor = conn.cursor()
    for shift in shifts:
        # UPSERT via executemany voor performance
        cursor.execute(...)
    conn.commit()
```

---

## Verlof Services

### VerlofRepo

**Locatie:** `src/services/repo/verlof_repo.py`

#### Constanten

```python
# Alleen deze codes zijn aanvraagbaar via verlof aanvraag scherm
VERLOF_AANVRAAG_CODES = ('VV', 'KD', 'VP')
```

#### `haal_alle_verloftypes()`

```python
@staticmethod
def haal_alle_verloftypes(alleen_aanvraagbaar: bool = False) -> List[Dict[str, Any]]
```

**Parameters:**
- `alleen_aanvraagbaar` (bool): Filter op aanvraagbare codes (VV, KD, VP)

**Returns:** Lijst met verloftype Dict objecten

**SQL (met filter):**
```sql
SELECT id, code, naam, term, ...
FROM special_codes
WHERE code IN ('VV', 'KD', 'VP')
ORDER BY code
```

---

#### `haal_aanvragen_voor_gebruiker()`

```python
@staticmethod
def haal_aanvragen_voor_gebruiker(gebruiker_id: int) -> List[Dict[str, Any]]
```

**Returns:** Verlofaanvragen van specifieke gebruiker

---

#### `haal_openstaande_aanvragen()`

```python
@staticmethod
def haal_openstaande_aanvragen() -> List[Dict[str, Any]]
```

**Returns:** Alle aanvragen met status 'pending'

**SQL:**
```sql
SELECT * FROM verlof_aanvragen
WHERE status = 'pending'
ORDER BY aangevraagd_op DESC
```

---

#### `maak_aanvraag()`

```python
@staticmethod
def maak_aanvraag(
    gebruiker_id: int,
    start_datum: str,
    eind_datum: str,
    aantal_dagen: int,
    toegekende_code_term: Optional[str],
    opmerking: Optional[str]
) -> int
```

**Returns:** ID van nieuwe aanvraag

---

#### `update_aanvraag_status()`

```python
@staticmethod
def update_aanvraag_status(
    aanvraag_id: int,
    status: str,
    behandeld_door: int,
    reden_weigering: Optional[str] = None
) -> None
```

**Doel:** Goedkeuren of afwijzen van aanvraag.

---

### VerlofService

**Locatie:** `src/services/applicatie/verlof_service.py`

#### `haal_alle_verloftypes()`

```python
@staticmethod
def haal_alle_verloftypes(alleen_aanvraagbaar: bool = False) -> List[VerlofType]
```

**Parameters:**
- `alleen_aanvraagbaar` (bool): Filter op aanvraagbare codes (VV, KD, VP)

**Returns:** `List[VerlofType]` - Domein objecten

**Gebruik:**
```python
# Voor dropdown in verlof aanvraag scherm
types = VerlofService.haal_alle_verloftypes(alleen_aanvraagbaar=True)
# => [VerlofType(VV), VerlofType(KD), VerlofType(VP)]

# Alle verloftypes (inclusief RX, CX, Z, etc.)
alle_types = VerlofService.haal_alle_verloftypes()
```

---

#### `maak_aanvraag()`

```python
@staticmethod
def maak_aanvraag(
    gebruiker_id: int,
    start_datum: str,
    eind_datum: str,
    opmerking: Optional[str] = None,
    toegekende_code_term: Optional[str] = None
) -> int
```

**Flow:**
```python
# 1. Bereken aantal dagen (domein functie)
aantal_dagen = verlof_domein.bereken_aantal_dagen(start_datum, eind_datum)

# 2. Valideer aanvraag data
is_geldig, fout = verlof_domein.valideer_verlof_aanvraag(...)
if not is_geldig:
    raise ValueError(fout)

# 3. Sla op via repo
return VerlofRepo.maak_aanvraag(...)
```

---

#### `goedkeuren_aanvraag()`

```python
@staticmethod
def goedkeuren_aanvraag(aanvraag_id: int, behandelaar_id: int) -> None
```

**Flow:** Update status naar 'goedgekeurd' via repo

---

#### `afwijzen_verlofaanvraag()`

```python
@staticmethod
def afwijzen_verlofaanvraag(
    aanvraag_id: int,
    behandelaar_id: int,
    reden: str
) -> None
```

**Flow:** Update status naar 'geweigerd' met reden via repo

**Raises:** `ValueError` als reden leeg is

---

### VerlofSaldoService

**Locatie:** `src/services/applicatie/verlof_saldo_service.py`

#### `bereken_fifo_verdeling()`

```python
@classmethod
def bereken_fifo_verdeling(
    cls, gebruiker_id: int, jaar: int, verlof_type: str = "VV"
) -> VerlofFifoVerdeling
```

**Doel:** Bereken FIFO-verdeling van verlof over huidig jaar en vorig jaar potten.

**Parameters:**
- `gebruiker_id` (int): ID van gebruiker
- `jaar` (int): Het jaar
- `verlof_type` (str): "VV" of "KD"

**Returns:** `VerlofFifoVerdeling` met gesplitste waardes per pot

**Flow:**
```python
# 1. Haal saldo en statistieken
saldo = VerlofSaldoRepo.haal_saldo(gebruiker_id, jaar)
stats = VerlofRepo.haal_verlof_statistieken(gebruiker_id, jaar)

# 2. Bepaal potten per verloftype
vorig_jaar_recht = saldo["verlof_overgedragen"]  # of kd_overgedragen
huidig_jaar_recht = saldo["verlof_totaal"]       # of kd_totaal

# 3. FIFO verdeling opgenomen: eerst uit vorig jaar
vorig_jaar_opgenomen = min(vorig_jaar_recht, totaal_opgenomen)
huidig_jaar_opgenomen = max(0, totaal_opgenomen - vorig_jaar_recht)

# 4. FIFO verdeling aangevraagd: uit restant vorig jaar
restant = vorig_jaar_recht - vorig_jaar_opgenomen
vorig_jaar_aangevraagd = min(restant, totaal_aangevraagd)
huidig_jaar_aangevraagd = max(0, totaal_aangevraagd - restant)

# 5. Bereken beschikbaar per pot
return VerlofFifoVerdeling(...)
```

**Gebruik:**
```python
from src.services.applicatie.verlof_saldo_service import VerlofSaldoService

fifo = VerlofSaldoService.bereken_fifo_verdeling(1, 2026, "VV")

# Banner logica
if fifo.vorig_jaar_beschikbaar > 0:
    print(f"Nog {fifo.vorig_jaar_beschikbaar} dagen voor 1 mei!")
```

---

#### `check_1_mei_waarschuwing()`

```python
@classmethod
def check_1_mei_waarschuwing(
    cls, gebruiker_id: int
) -> Tuple[bool, Optional[str], int]
```

**Doel:** Check of 1 mei waarschuwing getoond moet worden (FIFO-based).

**Returns:**
- `Tuple[bool, Optional[str], int]`
  - `toon_waarschuwing`: True als er resterende overgedragen dagen zijn
  - `bericht`: Waarschuwingstekst of None
  - `dagen_tot_1_mei`: Aantal dagen tot deadline

**Flow:** Gebruikt `bereken_fifo_verdeling()` om te bepalen of `vorig_jaar_beschikbaar > 0`

---

### VerlofRepo Statistieken

**Locatie:** `src/services/repo/verlof_repo.py`

#### `haal_verlof_statistieken()`

```python
@staticmethod
def haal_verlof_statistieken(
    gebruiker_id: int, jaar: int
) -> Dict[str, Dict[str, int]]
```

**Doel:** Haal verlof statistieken met correcte definities.

**⚠️ BELANGRIJKE DEFINITIES:**

| Veld | Definitie | SQL Filter |
|------|-----------|------------|
| `opgenomen` | Dagen met VV/KD code op planning die al gepasseerd zijn | `datum < date('now')` |
| `aangevraagd` | Dagen in actieve aanvragen (niet volledig opgenomen) | `status IN ('pending', 'goedgekeurd')` AND `eind_datum >= date('now')` |

**Returns:**
```python
{
    "VV": {"aangevraagd": 3, "opgenomen": 14},
    "KD": {"aangevraagd": 1, "opgenomen": 5}
}
```

**SQL (opgenomen):**
```sql
SELECT COUNT(*) FROM planning
WHERE gebruiker_id = ?
  AND strftime('%Y', datum) = ?
  AND shift_code = 'VV'
  AND datum < date('now')
```

**SQL (aangevraagd):**
```sql
SELECT COALESCE(SUM(aantal_dagen), 0) FROM verlof_aanvragen
WHERE gebruiker_id = ?
  AND strftime('%Y', start_datum) = ?
  AND status IN ('pending', 'goedgekeurd')
  AND toegekende_code_term = 'verlof'
  AND eind_datum >= date('now')
```

---

## Notities Services

### NotitieRepo

**Locatie:** `src/services/repo/notitie_repo.py`

#### `haal_notities_voor_gebruiker()`

```python
@staticmethod
def haal_notities_voor_gebruiker(
    gebruiker_id: int,
    alleen_ongelezen: bool = False
) -> List[Dict[str, Any]]
```

**Returns:** Notities voor gebruiker (specifiek + algemene meldingen)

**SQL:**
```sql
SELECT id, van_gebruiker_id, naar_gebruiker_id, planning_datum,
       bericht, is_gelezen, prioriteit, aangemaakt_op, gelezen_op
FROM notities
WHERE (naar_gebruiker_id = ? OR naar_gebruiker_id IS NULL)
  AND (? = 0 OR is_gelezen = 0)
ORDER BY aangemaakt_op DESC
```

---

#### `tel_ongelezen_notities()`

```python
@staticmethod
def tel_ongelezen_notities(gebruiker_id: int) -> int
```

**Returns:** Aantal ongelezen notities

---

#### `maak_notitie()`

```python
@staticmethod
def maak_notitie(
    van_gebruiker_id: int,
    naar_gebruiker_id: Optional[int],
    bericht: str,
    prioriteit: str,
    planning_datum: Optional[str] = None
) -> int
```

**Returns:** ID van nieuwe notitie

---

#### `markeer_als_gelezen()`

```python
@staticmethod
def markeer_als_gelezen(notitie_id: int) -> None
```

**SQL:**
```sql
UPDATE notities
SET is_gelezen = 1, gelezen_op = CURRENT_TIMESTAMP
WHERE id = ?
```

---

### NotitieService

**Locatie:** `src/services/applicatie/notitie_service.py`

#### `haal_notities_voor_gebruiker()`

```python
@staticmethod
def haal_notities_voor_gebruiker(
    gebruiker_id: int,
    alleen_ongelezen: bool = False
) -> List[Notitie]
```

**Returns:** `List[Notitie]` - Domein objecten

---

#### `maak_notitie()`

```python
@staticmethod
def maak_notitie(
    van_gebruiker_id: int,
    bericht: str,
    prioriteit: str = 'normaal',
    naar_gebruiker_id: Optional[int] = None,
    planning_datum: Optional[str] = None
) -> int
```

**Flow:** Valideer bericht + prioriteit → Sla op via repo

**Raises:** `ValueError` bij validatie fouten (lege bericht, ongeldige prioriteit)

---

#### `markeer_als_gelezen()`

```python
@staticmethod
def markeer_als_gelezen(notitie_id: int) -> None
```

---

## HR-Validatie Services

### HRRegelRepo

**Locatie:** `src/services/repo/hr_regel_repo.py`

#### `haal_alle_actieve_regels()`

```python
@staticmethod
def haal_alle_actieve_regels() -> List[Dict[str, Any]]
```

**Returns:** Alle actieve HR-regels

**SQL:**
```sql
SELECT id, code, naam, waarde, eenheid, ernst_niveau, beschrijving
FROM hr_regels
WHERE is_actief = 1
ORDER BY code
```

---

#### `haal_shift_tijden_mapping()`

```python
@staticmethod
def haal_shift_tijden_mapping() -> Dict[str, Dict[str, Any]]
```

**Returns:** Dict met shiftcode als key, metadata als value

**SQL:**
```sql
SELECT shiftcode, start_tijd, eind_tijd, is_nachtshift,
       is_rustdag, rustdag_type, telt_als_werkdag, uren_per_shift
FROM shift_tijden
```

**Voorbeeld return:**
```python
{
    "D": {
        "start_tijd": "06:00:00",
        "eind_tijd": "14:00:00",
        "is_nachtshift": 0,
        "telt_als_werkdag": 1,
        "uren_per_shift": 8.0
    },
    "N": {
        "start_tijd": "22:00:00",
        "eind_tijd": "06:00:00",
        "is_nachtshift": 1,  # Eindigt volgende dag!
        "telt_als_werkdag": 1,
        "uren_per_shift": 8.0
    }
}
```

---

#### `haal_rode_lijn_config()`

```python
@staticmethod
def haal_rode_lijn_config() -> Dict[str, Any]
```

**Returns:** Rode lijn configuratie (start datum, interval, max werkdagen)

---

#### `sla_override_op()`

```python
@staticmethod
def sla_override_op(
    shift_id: int,
    regel_code: str,
    overtreden_op: str,
    overridden_door: int,
    reden: str
) -> int
```

**Doel:** Registreer CRITICAL overtreding override in audit trail.

---

### HRValidatieService

**Locatie:** `src/services/applicatie/hr_validatie_service.py`

#### `haal_hr_config()`

```python
@classmethod
def haal_hr_config(cls, force_refresh: bool = False) -> HRConfig
```

**Doel:** Haal HR configuratie op (gecached).

**Returns:** `HRConfig` domein object

**Flow:**
```python
# 1. Check cache
if not force_refresh and cls._config_cache:
    return cls._config_cache

# 2. Haal data via repo
regels_rows = HRRegelRepo.haal_alle_actieve_regels()
shift_tijden = HRRegelRepo.haal_shift_tijden_mapping()
rode_lijn_cfg = HRRegelRepo.haal_rode_lijn_config()

# 3. Converteer naar HRConfig
regels_dict = {row['code']: row for row in regels_rows}
config = HRConfig(
    regels=regels_dict,
    shift_tijden=shift_tijden,
    rode_lijn_start=date.fromisoformat(rode_lijn_cfg['start_datum']),
    rode_lijn_interval=rode_lijn_cfg['interval']
)

# 4. Cache
cls._config_cache = config
return config
```

---

#### `valideer_maandplanning()`

```python
@classmethod
def valideer_maandplanning(
    cls,
    jaar: int,
    maand: int,
    force_refresh: bool = False
) -> ValidatieRapport
```

**Doel:** Valideer volledige maandplanning tegen alle HR-regels.

**Returns:** `ValidatieRapport` met overtredingen

**Flow:**
```python
# 1. Check cache
cache_key = (jaar, maand)
if not force_refresh and cache_key in cls._validatie_cache:
    return cls._validatie_cache[cache_key]

# 2. Haal config + shifts
config = cls.haal_hr_config()
shifts_data = PlanningRepo.haal_maand_shifts_bulk(jaar, maand)

# 3. Converteer naar domein shifts
shifts = cls._converteer_naar_domein_shifts(shifts_data, config)

# 4. Run alle validators (Strategy Pattern)
rapport = ValidatieRapport()
for validator in cls._validators:
    overtredingen = validator.valideer(shifts, config)
    rapport.voeg_toe_bulk(overtredingen)

# 5. Cache rapport
cls._validatie_cache[cache_key] = rapport
return rapport
```

**Validators (7 stuks):**
1. RodeLijnValidator
2. MaxDagenOpRijValidator
3. MaxUrenPerWeekValidator
4. MinRusttijdValidator
5. NachtshiftOpvolgingValidator
6. MaxWeekendsOpRijValidator
7. RXGapValidator

---

#### `valideer_shift_wijziging()`

```python
@classmethod
def valideer_shift_wijziging(
    cls,
    gebruiker_id: int,
    datum: date,
    nieuwe_shiftcode: Optional[str]
) -> ValidatieRapport
```

**Doel:** Incrementele validatie voor enkele shift wijziging.

**Returns:** `ValidatieRapport` met overtredingen voor deze gebruiker

**Flow:** Haal context shifts (7 dagen voor + na) → Simuleer wijziging → Run validators

---

#### `registreer_override()`

```python
@classmethod
def registreer_override(
    cls,
    shift_id: int,
    regel_code: str,
    overtreden_op: str,
    overridden_door: int,
    reden: str
) -> None
```

**Doel:** Registreer CRITICAL overtreding override in audit trail.

**Flow:** Valideer reden (min 10 chars) → Sla op via repo

---

#### `invalideer_cache()`

```python
@classmethod
def invalideer_cache(cls) -> None
```

**Doel:** Clear config + validatie cache (na config wijzigingen).

---

## Scherm Rechten Services

### SchermRechtenRepo

**Locatie:** `src/services/repo/scherm_rechten_repo.py`

#### `haal_rechten_voor_scherm()`

```python
@staticmethod
def haal_rechten_voor_scherm(scherm_id: str) -> List[Dict[str, Any]]
```

**Returns:** Rollen die toegang hebben tot scherm

---

### SchermRechtenService

**Locatie:** `src/services/applicatie/scherm_rechten_service.py`

#### `heeft_toegang()`

```python
@staticmethod
def heeft_toegang(gebruiker_rol: str, scherm_id: str) -> bool
```

**Doel:** Check of rol toegang heeft tot scherm.

**Returns:** `bool`

---

## Common Patterns

### 1. Service Methode Signature

**Repo:**
```python
@staticmethod
def methode_naam(params) -> ReturnType:
    """Docstring met SQL query."""
```

**Applicatie:**
```python
@staticmethod
def methode_naam(params) -> DomeinObject:
    """Docstring met flow beschrijving."""
```

### 2. Flow Pattern

**Applicatie service typische flow:**
```python
@staticmethod
def maak_object(params) -> int:
    # 1. Valideer input (domein functie)
    is_geldig, fout = valideer_functie(params)
    if not is_geldig:
        raise ValueError(fout)

    # 2. Business logic (domein functies)
    verwerkte_data = transformeer(params)

    # 3. Sla op via repo
    return Repo.maak_object(verwerkte_data)
```

### 3. Error Handling

**Repo:** Laat exceptions door
```python
# Repo
try:
    with get_db() as conn:
        cursor.execute(...)
except Exception as e:
    logger.error(f"Database fout: {e}", exc_info=True)
    raise  # Laat door naar applicatie
```

**Applicatie:** Vang op en raise betekenisvolle exceptions
```python
# Applicatie
try:
    return Repo.methode()
except Exception as e:
    logger.error(f"Fout bij operatie: {e}", exc_info=True)
    raise  # Of: raise ValueError("Begrijpelijke foutmelding")
```

### 4. Bulk Operations

**Gebruik `executemany()` voor > 5 records:**
```python
with get_db() as conn:
    cursor = conn.cursor()
    cursor.executemany(
        "INSERT INTO tabel VALUES (?, ?)",
        [(val1, val2), (val3, val4), ...]
    )
    conn.commit()
```

### 5. UPSERT Pattern

**INSERT or UPDATE on conflict:**
```python
INSERT INTO planning (gebruiker_id, datum, shift_code)
VALUES (?, ?, ?)
ON CONFLICT(gebruiker_id, datum)
DO UPDATE SET shift_code = ?
```

### 6. Cache Pattern

**Class-level cache in service:**
```python
class Service:
    _cache: Optional[Data] = None

    @classmethod
    def haal_data(cls, force_refresh: bool = False):
        if not force_refresh and cls._cache:
            return cls._cache

        data = Repo.haal_data()
        cls._cache = data
        return data

    @classmethod
    def invalideer_cache(cls):
        cls._cache = None
```

### 7. Factory + Mapping

**Repo → Dict, Service → Domein Object:**
```python
# Repo
rows = Repo.haal_objecten()  # List[Dict]

# Service
objecten = [DomeinObject.van_database_row(row) for row in rows]
```

### 8. Transactie Pattern

**Multiple operations in één transactie:**
```python
with get_db() as conn:
    cursor = conn.cursor()
    try:
        # Operatie 1
        cursor.execute(...)

        # Operatie 2
        cursor.execute(...)

        # Commit beide
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

---

## Zie Ook

- [Database Schema Referentie](./database_schema.md) - Database structuur
- [Domein Objecten Referentie](./domein_objecten.md) - Dataclasses en business logic
- [GUI Components Referentie](./gui_components.md) - UI widgets
- [Configuratie Referentie](./configuratie.md) - Systeem configuratie

---

**Einde Services API Referentie**
