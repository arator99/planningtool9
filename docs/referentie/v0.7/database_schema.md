# Database Schema Referentie

**Project**: Planningtool v0.7.x
**Database Type**: SQLite
**Laatst bijgewerkt**: 2026-03-01
**Versie**: v0.7.x

---

## Inhoudsopgave

1. [Overzicht](#overzicht)
2. [Metadata Tabellen](#metadata-tabellen)
3. [Gebruikers & Authenticatie](#gebruikers--authenticatie)
4. [Planning & Shifts](#planning--shifts)
5. [Referentie Tabellen](#referentie-tabellen)
6. [HR-Regelvalidatie](#hr-regelvalidatie)
7. [Communicatie](#communicatie)
8. [Competenties](#competenties)
9. [Foreign Keys & Relaties](#foreign-keys--relaties)
10. [Indices](#indices)

---

## Overzicht

De database bestaat uit **15+ tabellen** verdeeld over 7 functionale gebieden:

| Gebied | Tabellen | Beschrijving |
|--------|----------|--------------|
| Metadata | `db_metadata` | Versie tracking |
| Gebruikers | `gebruikers`, `scherm_rechten` | Authenticatie & autorisatie |
| Planning | `planning`, `planning_shifts` | Shift planning data |
| Referentie | `werkposten`, `shiftcodes`, `special_codes`, `competenties` | Type tabellen |
| Verlof | `verlof_aanvragen` | Verlofaanvragen beheer |
| HR-Validatie | `hr_regels`, `shift_tijden`, `planning_overrides`, `rode_lijnen` | Regelvalidatie systeem |
| Communicatie | `notities` | Berichten tussen gebruikers |
| Competenties | `gebruiker_competenties` | Vaardigheden koppeling |

---

## Metadata Tabellen

### `db_metadata`

Tracking van database versie en migraties.

```sql
CREATE TABLE db_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_number TEXT NOT NULL,
    migration_description TEXT,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Kolommen**:
| Kolom | Type | Constraints | Beschrijving |
|-------|------|-------------|--------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unieke identificator |
| `version_number` | TEXT | NOT NULL | Versie nummer (bijv. "0.7.8") |
| `migration_description` | TEXT | - | Beschrijving van migratie |
| `applied_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Wanneer migratie toegepast |

**Indices**: Geen

---

## Gebruikers & Authenticatie

### `gebruikers`

Centrale gebruikers tabel voor authenticatie en autorisatie.

```sql
CREATE TABLE gebruikers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gebruiker_uuid TEXT UNIQUE NOT NULL,
    gebruikersnaam TEXT UNIQUE NOT NULL,
    wachtwoord_hash BLOB NOT NULL,
    volledige_naam TEXT NOT NULL,
    voornaam TEXT,
    achternaam TEXT,
    rol TEXT NOT NULL CHECK(rol IN ('teamlid', 'planner', 'beheerder', 'admin')),
    is_reserve BOOLEAN DEFAULT 0,
    startweek_typedienst INTEGER CHECK(startweek_typedienst BETWEEN 1 AND 6),
    shift_voorkeuren TEXT,
    theme_voorkeur TEXT DEFAULT 'light',
    is_actief BOOLEAN DEFAULT 1,
    aangemaakt_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    gedeactiveerd_op TIMESTAMP,
    laatste_login TIMESTAMP
);
```

**Kolommen**:
| Kolom | Type | Constraints | Beschrijving |
|-------|------|-------------|--------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unieke identificator |
| `gebruiker_uuid` | TEXT | UNIQUE, NOT NULL | UUID voor externe referentie |
| `gebruikersnaam` | TEXT | UNIQUE, NOT NULL | Login naam |
| `wachtwoord_hash` | BLOB | NOT NULL | Bcrypt hash van wachtwoord |
| `volledige_naam` | TEXT | NOT NULL | Volledige naam voor weergave |
| `voornaam` | TEXT | - | Voornaam (optioneel) |
| `achternaam` | TEXT | - | Achternaam (optioneel) |
| `rol` | TEXT | CHECK constraint | `'teamlid'`, `'planner'`, `'beheerder'`, `'admin'` |
| `is_reserve` | BOOLEAN | DEFAULT 0 | Reserve medewerker flag |
| `startweek_typedienst` | INTEGER | CHECK (1-6) | Type dienst startweek |
| `shift_voorkeuren` | TEXT | - | JSON met shift voorkeuren |
| `theme_voorkeur` | TEXT | DEFAULT 'light' | `'light'` of `'dark'` |
| `is_actief` | BOOLEAN | DEFAULT 1 | Actief/inactief status |
| `aangemaakt_op` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Aanmaak tijdstip |
| `gedeactiveerd_op` | TIMESTAMP | - | Deactivatie tijdstip (NULL indien actief) |
| `laatste_login` | TIMESTAMP | - | Laatste login tijdstip |

**Indices**: Automatisch op UNIQUE kolommen

**⚠️ BELANGRIJK**:
- Rol `'gebruiker'` is **verwijderd** in v0.7.2 (gebruik `'teamlid'`)
- Wachtwoord hash gebruikt **bcrypt** met minimum 12 rounds

---

### `scherm_rechten`

Scherm-gebaseerde toegangscontrole per rol.

```sql
CREATE TABLE scherm_rechten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scherm_id TEXT NOT NULL,
    rol TEXT NOT NULL,
    toegang_toegestaan BOOLEAN DEFAULT 1,
    aangepast_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(scherm_id, rol)
);

CREATE INDEX idx_scherm_rechten_lookup
ON scherm_rechten(scherm_id, rol);
```

**Kolommen**:
| Kolom | Type | Constraints | Beschrijving |
|-------|------|-------------|--------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unieke identificator |
| `scherm_id` | TEXT | NOT NULL | Scherm identificator (bijv. "gebruikers_beheer") |
| `rol` | TEXT | NOT NULL | Rol naam |
| `toegang_toegestaan` | BOOLEAN | DEFAULT 1 | Toegang flag |
| `aangepast_op` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Laatste wijziging |

**Indices**:
- `idx_scherm_rechten_lookup` op `(scherm_id, rol)` - snelle toegangscontrole

---

## Planning & Shifts

### `planning`

Hoofdtabel voor planning shifts.

```sql
CREATE TABLE planning (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gebruiker_id INTEGER NOT NULL,
    datum DATE NOT NULL,
    shift_code TEXT,
    notitie TEXT,
    notitie_gelezen BOOLEAN DEFAULT 0,
    status TEXT DEFAULT 'concept',
    aangemaakt_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(gebruiker_id, datum),
    FOREIGN KEY (gebruiker_id) REFERENCES gebruikers(id) ON DELETE CASCADE
);
```

**Kolommen**:
| Kolom | Type | Constraints | Beschrijving |
|-------|------|-------------|--------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unieke identificator |
| `gebruiker_id` | INTEGER | NOT NULL, FOREIGN KEY | Verwijzing naar gebruiker |
| `datum` | DATE | NOT NULL | Planning datum (ISO format YYYY-MM-DD) |
| `shift_code` | TEXT | - | Shiftcode (NULL = vrije dag) |
| `notitie` | TEXT | - | Optionele notitie bij shift |
| `notitie_gelezen` | BOOLEAN | DEFAULT 0 | Notitie gelezen status |
| `status` | TEXT | DEFAULT 'concept' | `'concept'` of `'gepubliceerd'` |
| `aangemaakt_op` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Aanmaak tijdstip |

**Unique Constraint**: `(gebruiker_id, datum)` - één shift per gebruiker per dag

**Foreign Keys**:
- `gebruiker_id` → `gebruikers(id)` ON DELETE CASCADE

**⚠️ BELANGRIJK**:
- `shift_code` kan NULL zijn (vrije dag)
- Datum formaat: **YYYY-MM-DD** (ISO 8601)
- Unique constraint voorkomt dubbele shifts

---

## Referentie Tabellen

### `werkposten` (Post)

Werkposten/functies binnen het team.

**⚠️ Let op**: Heet `werkposten` in database, maar domein object is `Post`

```sql
CREATE TABLE werkposten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    naam TEXT NOT NULL,
    beschrijving TEXT,
    telt_als_werkdag BOOLEAN DEFAULT 1,
    reset_12u_rust BOOLEAN DEFAULT 0,
    breekt_werk_reeks BOOLEAN DEFAULT 0,
    is_actief BOOLEAN DEFAULT 1,
    aangemaakt_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    gedeactiveerd_op TIMESTAMP
);
```

**Kolommen**:
| Kolom | Type | Constraints | Beschrijving |
|-------|------|-------------|--------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unieke identificator |
| `naam` | TEXT | NOT NULL | Naam werkpost (bijv. "Operatie", "Controle") |
| `beschrijving` | TEXT | - | Uitgebreide beschrijving |
| `telt_als_werkdag` | BOOLEAN | DEFAULT 1 | Telt mee als gewerkte dag |
| `reset_12u_rust` | BOOLEAN | DEFAULT 0 | Reset 12-uur rust regel |
| `breekt_werk_reeks` | BOOLEAN | DEFAULT 0 | Breekt reeks werkdagen |
| `is_actief` | BOOLEAN | DEFAULT 1 | Actief/inactief status |
| `aangemaakt_op` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Aanmaak tijdstip |
| `gedeactiveerd_op` | TIMESTAMP | - | Deactivatie tijdstip |

**⚠️ MAPPING ISSUES**:
- Post object heeft **GEEN** `code` veld (alleen `naam`)
- UI verwachtte eerder `post.code` - dit is gefixed

---

### `shiftcodes`

Shift codes met timing en metadata.

```sql
CREATE TABLE shiftcodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    werkpost_id INTEGER,
    dag_type TEXT,
    shift_type TEXT,
    code TEXT NOT NULL,
    start_uur TEXT,
    eind_uur TEXT,
    is_kritisch BOOLEAN DEFAULT 0,
    FOREIGN KEY (werkpost_id) REFERENCES werkposten(id)
);
```

**Kolommen**:
| Kolom | Type | Constraints | Beschrijving |
|-------|------|-------------|--------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unieke identificator |
| `werkpost_id` | INTEGER | FOREIGN KEY | Gekoppelde werkpost (optioneel) |
| `dag_type` | TEXT | - | Type dag ('werkdag', 'weekend', 'feestdag') |
| `shift_type` | TEXT | - | Type dienst ('early', 'late', 'night') |
| `code` | TEXT | NOT NULL | Shiftcode (bijv. "DE", "DL", "DN") |
| `start_uur` | TEXT | - | Start tijd (HH:MM format, bijv. "06:00") |
| `eind_uur` | TEXT | - | Eind tijd (HH:MM format, bijv. "14:00") |
| `is_kritisch` | BOOLEAN | DEFAULT 0 | Kritische shift flag |

**⚠️ MAPPING ISSUES**:
- Shiftcode object heeft **GEEN** `beschrijving` veld
- Shiftcode object heeft **GEEN** `is_actief` veld (gebruikt `is_kritisch`)
- Velden: `start_uur`/`eind_uur` (NIET `start_tijd`/`eind_tijd`)

---

## HR-Regelvalidatie

### `hr_regels`

Configureerbare HR-validatieregels.

```sql
CREATE TABLE hr_regels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(50) UNIQUE NOT NULL,
    naam VARCHAR(100) NOT NULL,
    waarde INTEGER,
    waarde_extra VARCHAR(50),
    eenheid VARCHAR(20),
    ernst_niveau VARCHAR(20) DEFAULT 'WARNING',
    is_actief BOOLEAN DEFAULT 1,
    beschrijving TEXT,
    aangemaakt_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    gewijzigd_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_hr_regels_code ON hr_regels(code);
CREATE INDEX idx_hr_regels_actief ON hr_regels(is_actief);
```

**Kolommen**:
| Kolom | Type | Constraints | Beschrijving |
|-------|------|-------------|--------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unieke identificator |
| `code` | VARCHAR(50) | UNIQUE, NOT NULL | Regel code (bijv. "MAX_DAGEN_RIJ") |
| `naam` | VARCHAR(100) | NOT NULL | Weergave naam |
| `waarde` | INTEGER | - | Drempelwaarde (bijv. 7 voor max dagen) |
| `waarde_extra` | VARCHAR(50) | - | Extra waarde voor complexe regels |
| `eenheid` | VARCHAR(20) | - | 'dagen', 'uren', 'aantal', 'tijd' |
| `ernst_niveau` | VARCHAR(20) | DEFAULT 'WARNING' | 'INFO', 'WARNING', 'CRITICAL' |
| `is_actief` | BOOLEAN | DEFAULT 1 | Actief/inactief status |
| `beschrijving` | TEXT | - | Uitleg van de regel |
| `aangemaakt_op` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Aanmaak tijdstip |
| `gewijzigd_op` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Laatste wijziging |

**Standaard Regels** (7 stuks):
| Code | Naam | Waarde | Eenheid | Ernst |
|------|------|--------|---------|-------|
| `RODE_LIJN_DAGEN` | Rode Lijn Cyclus | 28 | dagen | INFO |
| `RODE_LIJN_MAX_WERK` | Max Werkdagen Per Periode | 19 | dagen | WARNING |
| `MAX_DAGEN_RIJ` | Max Dagen Op Rij | 7 | dagen | WARNING |
| `MAX_UREN_WEEK` | Max Uren Per Week | 50 | uren | CRITICAL |
| `MIN_RUSTTIJD` | Minimale Rusttijd | 11 | uren | CRITICAL |
| `MAX_WEEKENDS_RIJ` | Max Weekends Op Rij | 6 | aantal | WARNING |
| `RX_MAX_GAP` | RX Rustdag Gap | 7 | dagen | WARNING |

**Indices**:
- `idx_hr_regels_code` op `code` - snelle lookup per regel
- `idx_hr_regels_actief` op `is_actief` - filter actieve regels

---

### `shift_tijden`

Mapping van shiftcodes naar tijden en metadata (voor HR-validatie).

```sql
CREATE TABLE shift_tijden (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shiftcode VARCHAR(10) UNIQUE NOT NULL,
    start_tijd TIME,
    eind_tijd TIME,
    is_nachtshift BOOLEAN DEFAULT 0,
    is_rustdag BOOLEAN DEFAULT 0,
    rustdag_type VARCHAR(10),
    telt_als_werkdag BOOLEAN DEFAULT 1,
    uren_per_shift DECIMAL(4,2),
    FOREIGN KEY (shiftcode) REFERENCES shiftcodes(code)
);

CREATE INDEX idx_shift_tijden_code ON shift_tijden(shiftcode);
```

**Kolommen**:
| Kolom | Type | Constraints | Beschrijving |
|-------|------|-------------|--------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unieke identificator |
| `shiftcode` | VARCHAR(10) | UNIQUE, NOT NULL | Shiftcode (bijv. "D", "L", "N") |
| `start_tijd` | TIME | - | Start tijd (HH:MM:SS, NULL voor rustdagen) |
| `eind_tijd` | TIME | - | Eind tijd (HH:MM:SS, NULL voor rustdagen) |
| `is_nachtshift` | BOOLEAN | DEFAULT 0 | Shift overschrijdt middernacht |
| `is_rustdag` | BOOLEAN | DEFAULT 0 | Is dit een rustdag |
| `rustdag_type` | VARCHAR(10) | - | 'RXW', 'RXF', 'CXW', 'CXA', NULL |
| `telt_als_werkdag` | BOOLEAN | DEFAULT 1 | Telt voor rode lijn berekening |
| `uren_per_shift` | DECIMAL(4,2) | - | Uren (bijv. 8.0, NULL voor rustdagen) |

**Standaard Shifts** (10 stuks):
| Shiftcode | Start | Eind | Nacht | Rustdag | Type | Werkdag | Uren |
|-----------|-------|------|-------|---------|------|---------|------|
| `D` | 06:00 | 14:00 | 0 | 0 | NULL | 1 | 8.0 |
| `L` | 14:00 | 22:00 | 0 | 0 | NULL | 1 | 8.0 |
| `N` | 22:00 | 06:00 | **1** | 0 | NULL | 1 | 8.0 |
| `RXW` | NULL | NULL | 0 | 1 | RXW | 0 | NULL |
| `RXF` | NULL | NULL | 0 | 1 | RXF | 0 | NULL |
| `CXW` | NULL | NULL | 0 | 1 | CXW | 0 | NULL |
| `CXA` | NULL | NULL | 0 | 1 | CXA | 0 | NULL |
| `Z` | NULL | NULL | 0 | 1 | NULL | 0 | NULL |
| `V` | NULL | NULL | 0 | 1 | NULL | 0 | NULL |
| `DA` | NULL | NULL | 0 | 1 | NULL | 0 | NULL |

**⚠️ BELANGRIJK**:
- Nachtshift (`N`) heeft `is_nachtshift = 1` (eindigt volgende dag!)
- RX* vs CX* distinctie: **CX* telt NIET voor RX gap regel**

---

### `planning_overrides`

Audit trail voor geaccepteerde CRITICAL overtredingen.

```sql
CREATE TABLE planning_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    planning_shift_id INTEGER NOT NULL,
    regel_code VARCHAR(50) NOT NULL,
    ernst_niveau VARCHAR(20) NOT NULL,
    overtreding_bericht TEXT NOT NULL,
    reden_afwijking TEXT,
    goedgekeurd_door INTEGER,
    goedgekeurd_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (planning_shift_id) REFERENCES planning_shifts(id) ON DELETE CASCADE,
    FOREIGN KEY (regel_code) REFERENCES hr_regels(code),
    FOREIGN KEY (goedgekeurd_door) REFERENCES gebruikers(id)
);

CREATE INDEX idx_overrides_shift ON planning_overrides(planning_shift_id);
CREATE INDEX idx_overrides_regel ON planning_overrides(regel_code);
CREATE INDEX idx_overrides_goedkeurder ON planning_overrides(goedgekeurd_door);
CREATE INDEX idx_overrides_datum ON planning_overrides(goedgekeurd_op);
```

**Kolommen**:
| Kolom | Type | Constraints | Beschrijving |
|-------|------|-------------|--------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unieke identificator |
| `planning_shift_id` | INTEGER | NOT NULL, FOREIGN KEY | Verwijzing naar planning shift |
| `regel_code` | VARCHAR(50) | NOT NULL, FOREIGN KEY | Regel code (bijv. "MIN_RUSTTIJD") |
| `ernst_niveau` | VARCHAR(20) | NOT NULL | Ernst (altijd "CRITICAL" voor overrides) |
| `overtreding_bericht` | TEXT | NOT NULL | Foutmelding (bijv. "Slechts 9u rust") |
| `reden_afwijking` | TEXT | - | Door planner ingevulde reden (verplicht!) |
| `goedgekeurd_door` | INTEGER | FOREIGN KEY | Gebruiker ID van planner |
| `goedgekeurd_op` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Wanneer goedgekeurd |

**Indices**:
- `idx_overrides_shift` op `planning_shift_id`
- `idx_overrides_regel` op `regel_code`
- `idx_overrides_goedkeurder` op `goedgekeurd_door`
- `idx_overrides_datum` op `goedgekeurd_op`

**⚠️ BELANGRIJK**:
- Alleen **CRITICAL** overtredingen worden gelogd
- `reden_afwijking` is **verplicht** (min 10 karakters)

---

### `rode_lijnen`

Configuratie voor rode lijn cyclus.

```sql
CREATE TABLE rode_lijnen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_datum DATE NOT NULL,
    interval_dagen INTEGER DEFAULT 28,
    is_actief BOOLEAN DEFAULT 1,
    aangemaakt_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_rode_lijnen_datum ON rode_lijnen(start_datum);
CREATE INDEX idx_rode_lijnen_actief ON rode_lijnen(is_actief);
```

**Kolommen**:
| Kolom | Type | Constraints | Beschrijving |
|-------|------|-------------|--------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unieke identificator |
| `start_datum` | DATE | NOT NULL | Eerste rode lijn datum (bijv. 2026-01-01) |
| `interval_dagen` | INTEGER | DEFAULT 28 | Elke X dagen een rode lijn |
| `is_actief` | BOOLEAN | DEFAULT 1 | Actieve configuratie (slechts 1) |
| `aangemaakt_op` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Aanmaak tijdstip |

**Standaard Configuratie**:
- Start datum: **2026-01-01**
- Interval: **28 dagen**

---

## Communicatie

### `notities`

Berichten/notities tussen gebruikers en planners.

```sql
CREATE TABLE notities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    van_gebruiker_id INTEGER NOT NULL,
    naar_gebruiker_id INTEGER,
    planning_datum DATE,
    bericht TEXT NOT NULL,
    is_gelezen BOOLEAN DEFAULT 0,
    prioriteit TEXT CHECK(prioriteit IN ('laag', 'normaal', 'hoog')) DEFAULT 'normaal',
    aangemaakt_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    gelezen_op TIMESTAMP,
    FOREIGN KEY (van_gebruiker_id) REFERENCES gebruikers(id) ON DELETE CASCADE,
    FOREIGN KEY (naar_gebruiker_id) REFERENCES gebruikers(id) ON DELETE CASCADE
);

CREATE INDEX idx_notities_ontvanger ON notities(naar_gebruiker_id, is_gelezen);
CREATE INDEX idx_notities_planning_datum ON notities(planning_datum);
CREATE INDEX idx_notities_aangemaakt_op ON notities(aangemaakt_op DESC);
```

**Kolommen**:
| Kolom | Type | Constraints | Beschrijving |
|-------|------|-------------|--------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unieke identificator |
| `van_gebruiker_id` | INTEGER | NOT NULL, FOREIGN KEY | Afzender |
| `naar_gebruiker_id` | INTEGER | FOREIGN KEY | Ontvanger (NULL = broadcast) |
| `planning_datum` | DATE | - | Gerelateerde planning datum |
| `bericht` | TEXT | NOT NULL | Bericht tekst |
| `is_gelezen` | BOOLEAN | DEFAULT 0 | Gelezen status |
| `prioriteit` | TEXT | CHECK constraint | 'laag', 'normaal', 'hoog' |
| `aangemaakt_op` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Aanmaak tijdstip |
| `gelezen_op` | TIMESTAMP | - | Wanneer gelezen (NULL = ongelezen) |

**Indices**:
- `idx_notities_ontvanger` op `(naar_gebruiker_id, is_gelezen)` - ongelezen berichten
- `idx_notities_planning_datum` op `planning_datum`
- `idx_notities_aangemaakt_op` op `aangemaakt_op DESC` - chronologische volgorde

---

## Verlof

### `verlof_aanvragen`

Verlofaanvragen van medewerkers.

```sql
CREATE TABLE verlof_aanvragen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gebruiker_id INTEGER NOT NULL,
    start_datum DATE NOT NULL,
    eind_datum DATE NOT NULL,
    aantal_dagen INTEGER NOT NULL,
    status TEXT CHECK(status IN ('pending', 'goedgekeurd', 'geweigerd')) DEFAULT 'pending',
    toegekende_code_term TEXT,
    opmerking TEXT,
    aangevraagd_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    behandeld_door INTEGER,
    behandeld_op TIMESTAMP,
    reden_weigering TEXT,
    ingediend_door INTEGER,  -- v0.7.50: Namens-aanvraag functionaliteit
    FOREIGN KEY (gebruiker_id) REFERENCES gebruikers(id) ON DELETE CASCADE,
    FOREIGN KEY (behandeld_door) REFERENCES gebruikers(id),
    FOREIGN KEY (ingediend_door) REFERENCES gebruikers(id)
);
```

**Kolommen**:
| Kolom | Type | Constraints | Beschrijving |
|-------|------|-------------|--------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unieke identificator |
| `gebruiker_id` | INTEGER | NOT NULL, FOREIGN KEY | **Ontvanger** van verlof |
| `start_datum` | DATE | NOT NULL | Start verlof periode |
| `eind_datum` | DATE | NOT NULL | Eind verlof periode |
| `aantal_dagen` | INTEGER | NOT NULL | Berekend aantal dagen |
| `status` | TEXT | CHECK constraint | **'pending', 'goedgekeurd', 'geweigerd'** |
| `toegekende_code_term` | TEXT | - | Verloftype code (VV, KD, VP) |
| `opmerking` | TEXT | - | Opmerking/reden van aanvrager |
| `aangevraagd_op` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Aanvraag tijdstip |
| `behandeld_door` | INTEGER | FOREIGN KEY | Planner die goedkeurde/weigerde |
| `behandeld_op` | TIMESTAMP | - | Behandel tijdstip |
| `reden_weigering` | TEXT | - | Reden bij weigering |
| `ingediend_door` | INTEGER | FOREIGN KEY, **v0.7.50** | Planner die namens aanvroeg (NULL = gebruiker zelf) |

**⚠️ KRITIEK - Status CHECK Constraint:**
```sql
CHECK(status IN ('pending', 'goedgekeurd', 'geweigerd'))
```

Status waarden:
- `'pending'` - Openstaand, wacht op behandeling
- `'goedgekeurd'` - Goedgekeurd door planner/beheerder
- `'geweigerd'` - Geweigerd door planner/beheerder

**Semantiek (v0.7.50)**:
- `gebruiker_id`: Wie **ontvangt** het verlof (ontvanger)
- `ingediend_door`: Wie heeft de aanvraag **ingediend** (indiener)
  - `NULL` = aanvraag door gebruiker zelf (normaal)
  - `<ID>` = planner die namens gebruiker aanvroeg
- `behandeld_door`: Wie heeft de aanvraag **goedgekeurd/geweigerd**

**Foreign Keys**:
- `gebruiker_id` → `gebruikers(id)` ON DELETE CASCADE
- `behandeld_door` → `gebruikers(id)`
- `ingediend_door` → `gebruikers(id)`

**Indices**:
- `idx_verlof_gebruiker_status` op `(gebruiker_id, status)` - eigen aanvragen filteren
- `idx_verlof_ingediend_door` op `ingediend_door` - namens-aanvragen vinden

---

### `special_codes` (Verloftypes)

Type tabellen voor verlof en andere speciale codes.

```sql
CREATE TABLE special_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    naam TEXT NOT NULL,
    term TEXT,
    telt_als_werkdag BOOLEAN DEFAULT 0,
    reset_12u_rust BOOLEAN DEFAULT 0,
    breekt_werk_reeks BOOLEAN DEFAULT 0
);
```

**Standaard Verlof Codes** (aanvraagbaar via UI):
| Code | Naam | Beschrijving |
|------|------|--------------|
| `VV` | Verlof | Regulier verlof |
| `KD` | Kompensatiedag | Compensatie |
| `VP` | Politiek Verlof | Politiek verlof |

**Andere Special Codes** (niet aanvraagbaar, alleen planning):
| Code | Beschrijving |
|------|--------------|
| `RXW`, `RXF` | Rustdag codes |
| `CXW`, `CXA` | Compensatie codes |
| `Z` | Ziekte |

---

## Competenties

### `competenties`

Master tabel met competenties/vaardigheden.

```sql
CREATE TABLE competenties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    naam TEXT NOT NULL UNIQUE,
    beschrijving TEXT,
    categorie TEXT,
    is_actief BOOLEAN DEFAULT 1,
    aangemaakt_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    gedeactiveerd_op TIMESTAMP
);

CREATE INDEX idx_competenties_naam ON competenties(naam);
CREATE INDEX idx_competenties_actief ON competenties(is_actief);
```

**Kolommen**:
| Kolom | Type | Constraints | Beschrijving |
|-------|------|-------------|--------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unieke identificator |
| `naam` | TEXT | NOT NULL, UNIQUE | Competentie naam |
| `beschrijving` | TEXT | - | Uitgebreide beschrijving |
| `categorie` | TEXT | - | Categorie (optioneel) |
| `is_actief` | BOOLEAN | DEFAULT 1 | Actief/inactief status |
| `aangemaakt_op` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Aanmaak tijdstip |
| `gedeactiveerd_op` | TIMESTAMP | - | Deactivatie tijdstip |

**Indices**:
- `idx_competenties_naam` op `naam` - snelle lookup
- `idx_competenties_actief` op `is_actief` - filter actieve competenties

---

### `gebruiker_competenties`

Koppeltabel gebruikers ↔ competenties (veel-op-veel).

```sql
CREATE TABLE gebruiker_competenties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gebruiker_id INTEGER NOT NULL,
    competentie_id INTEGER NOT NULL,
    niveau TEXT CHECK(niveau IN ('basis', 'gevorderd', 'expert')),
    geldig_tot DATE,
    aangemaakt_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (gebruiker_id) REFERENCES gebruikers(id) ON DELETE CASCADE,
    FOREIGN KEY (competentie_id) REFERENCES competenties(id) ON DELETE CASCADE,
    UNIQUE(gebruiker_id, competentie_id)
);

CREATE INDEX idx_gebruiker_competenties_gebruiker ON gebruiker_competenties(gebruiker_id);
CREATE INDEX idx_gebruiker_competenties_competentie ON gebruiker_competenties(competentie_id);
```

**Kolommen**:
| Kolom | Type | Constraints | Beschrijving |
|-------|------|-------------|--------------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | Unieke identificator |
| `gebruiker_id` | INTEGER | NOT NULL, FOREIGN KEY | Verwijzing naar gebruiker |
| `competentie_id` | INTEGER | NOT NULL, FOREIGN KEY | Verwijzing naar competentie |
| `niveau` | TEXT | CHECK constraint | 'basis', 'gevorderd', 'expert' |
| `geldig_tot` | DATE | - | Vervaldatum (optioneel) |
| `aangemaakt_op` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Aanmaak tijdstip |

**Unique Constraint**: `(gebruiker_id, competentie_id)` - één niveau per competentie per gebruiker

**Indices**:
- `idx_gebruiker_competenties_gebruiker` op `gebruiker_id`
- `idx_gebruiker_competenties_competentie` op `competentie_id`

---

## Foreign Keys & Relaties

### Relatie Diagram

```
gebruikers (1) ──── (*) planning
gebruikers (1) ──── (*) verlof_aanvragen (als aanvrager)
gebruikers (1) ──── (*) verlof_aanvragen (als behandelaar)
gebruikers (1) ──── (*) gebruiker_competenties
gebruikers (1) ──── (*) notities (als verzender)
gebruikers (1) ──── (*) notities (als ontvanger)
gebruikers (1) ──── (*) planning_overrides (als goedkeurder)

competenties (1) ──── (*) gebruiker_competenties

planning (1) ──── (*) planning_overrides

hr_regels (1) ──── (*) planning_overrides

werkposten (1) ──── (*) shiftcodes

shiftcodes (1) ──── (*) shift_tijden
```

### Foreign Key Constraints

| Tabel | Kolom | Referentie | ON DELETE |
|-------|-------|------------|-----------|
| `planning` | `gebruiker_id` | `gebruikers(id)` | CASCADE |
| `verlof_aanvragen` | `gebruiker_id` | `gebruikers(id)` | CASCADE |
| `verlof_aanvragen` | `behandeld_door` | `gebruikers(id)` | - |
| `gebruiker_competenties` | `gebruiker_id` | `gebruikers(id)` | CASCADE |
| `gebruiker_competenties` | `competentie_id` | `competenties(id)` | CASCADE |
| `notities` | `van_gebruiker_id` | `gebruikers(id)` | CASCADE |
| `notities` | `naar_gebruiker_id` | `gebruikers(id)` | CASCADE |
| `planning_overrides` | `planning_shift_id` | `planning_shifts(id)` | CASCADE |
| `planning_overrides` | `regel_code` | `hr_regels(code)` | - |
| `planning_overrides` | `goedgekeurd_door` | `gebruikers(id)` | - |
| `shiftcodes` | `werkpost_id` | `werkposten(id)` | - |
| `shift_tijden` | `shiftcode` | `shiftcodes(code)` | - |

---

## Indices

### Overzicht van alle indices

| Index Naam | Tabel | Kolom(men) | Doel |
|------------|-------|-----------|------|
| `idx_scherm_rechten_lookup` | scherm_rechten | (scherm_id, rol) | Snelle toegangscontrole |
| `idx_hr_regels_code` | hr_regels | code | Regel lookup |
| `idx_hr_regels_actief` | hr_regels | is_actief | Filter actieve regels |
| `idx_shift_tijden_code` | shift_tijden | shiftcode | Shift metadata lookup |
| `idx_overrides_shift` | planning_overrides | planning_shift_id | Override per shift |
| `idx_overrides_regel` | planning_overrides | regel_code | Override per regel |
| `idx_overrides_goedkeurder` | planning_overrides | goedgekeurd_door | Override per planner |
| `idx_overrides_datum` | planning_overrides | goedgekeurd_op | Chronologische lookup |
| `idx_rode_lijnen_datum` | rode_lijnen | start_datum | Datum berekeningen |
| `idx_rode_lijnen_actief` | rode_lijnen | is_actief | Actieve configuratie |
| `idx_notities_ontvanger` | notities | (naar_gebruiker_id, is_gelezen) | Ongelezen berichten |
| `idx_notities_planning_datum` | notities | planning_datum | Notities bij datum |
| `idx_notities_aangemaakt_op` | notities | aangemaakt_op DESC | Chronologisch |
| `idx_competenties_naam` | competenties | naam | Naam lookup |
| `idx_competenties_actief` | competenties | is_actief | Filter actieve |
| `idx_gebruiker_competenties_gebruiker` | gebruiker_competenties | gebruiker_id | Per gebruiker |
| `idx_gebruiker_competenties_competentie` | gebruiker_competenties | competentie_id | Per competentie |

---

## Veelvoorkomende Valkuilen

### ❌ Verkeerde Veldnamen

**Probleem**: UI code gebruikte verkeerde veldnamen

| Object | ❌ Verkeerd | ✅ Correct |
|--------|------------|-----------|
| Post | `post.code` | `post.naam` |
| Shiftcode | `shift.beschrijving` | `shift.shift_type` |
| Shiftcode | `shift.start_tijd` | `shift.start_uur` |
| Shiftcode | `shift.is_actief` | `shift.is_kritisch` |

### ❌ Rol 'gebruiker' vs 'teamlid'

**Probleem**: Oude code gebruikte `rol = 'gebruiker'`

✅ **Correct**: Gebruik `rol = 'teamlid'` (sinds v0.7.2)

### ❌ Datum Formaat

**Probleem**: Inconsistent datum formaat

✅ **Correct**: Gebruik **ISO 8601** format: `YYYY-MM-DD` (bijv. "2026-01-10")

---

## Migratie Historie

| Versie | Datum | Beschrijving |
|--------|-------|--------------|
| v0.6.x | - | Legacy versie |
| v0.7.0 | 2026-01-08 | scherm_rechten, rol constraint uitbreiding |
| v0.7.2 | 2026-01-09 | Verwijdering 'gebruiker' rol |
| v0.7.3 | 2026-01-09 | competenties, gebruiker_competenties |
| v0.7.5 | 2026-01-09 | notities |
| v0.7.8 | 2026-01-10 | HR-regels systeem (4 tabellen) |

---

**Laatste update**: 2026-01-16
**Versie**: v0.7.9
**Auteur**: Planningtool Development Team
