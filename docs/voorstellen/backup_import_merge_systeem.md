# Voorstel: Backup, Import & Merge systeem (super_beheerder)

**Status:** geïmplementeerd — 2026-03-22
**Datum:** 2026-03-22
**Scope:** super_beheerder-only GUI voor database-beheer

### Beslissingen (2026-03-22)

| Vraag | Beslissing |
|---|---|
| Merge-scope | Eenmalige v0.7→v0.9 migratie (PAT + TO), optie open voor toekomstige imports |
| Werkposten Supervisor/SuperVisor | Zelfde werkpost → samenvoegen op naam (case-insensitive) |
| Conflict-strategie | Skip bestaande records (UUID-gebaseerd, fallback op semantische sleutel) |
| Merge-formaat | JSON export/import voor toekomstige GUI-imports |
| Eenmalige migratie | Uitbreiding van `scripts/migreer_sqlite.py` voor meerdere bestanden |

---

## 1. Overzicht

Drie samenhangende functies via één beheermodule (`/beheer/database`):

| Functie | Omschrijving |
|---|---|
| **Backup** | Automatisch (dagelijks/wekelijks/maandelijks) + handmatig via GUI |
| **Restore** | Upload een backup → vervangt volledige database |
| **Merge** | Upload een backup van een andere instantie → voeg samen met huidige database |

---

## 2. Technische vertaling (PostgreSQL vs. SQLite)

In v0.7 was backup = `shutil.copy2(db.sqlite, backup_dir)` — triviaal bij SQLite.
In v0.9 draaien we PostgreSQL in Docker → andere aanpak nodig.

### 2a. Formaat: SQL dump via `pg_dump`

```
pg_dump -U $DB_USER -d $DB_NAME --no-owner --no-acl -F c -f backup.dump
```

- Formaat: **PostgreSQL custom format** (`.dump`) — compact, supports selective restore
- Opgeslagen in Docker volume `/backups` → gemount op NAS-pad

### 2b. Restore via `pg_restore`

```
pg_restore -U $DB_USER -d $DB_NAME --clean --if-exists backup.dump
```

- Maakt eerst automatisch een pre-restore backup
- Vervangt **alle** data in de bestaande database

### 2c. Merge: twee opties

**Optie A: pg_dump → tijdelijk schema → INSERT ON CONFLICT SKIP**

1. Laad geüploadde dump in tijdelijk PostgreSQL schema (bv. `merge_import`)
2. Per tabel: `INSERT INTO public.tabel SELECT * FROM merge_import.tabel ON CONFLICT (uuid) DO NOTHING`
3. Verwijder tijdelijk schema

Voordelen: SQL-native, betrouwbaar, atomisch per tabel
Nadelen: vereist `pg_restore` naar temp schema — complexer

**Optie B: Custom JSON export/import ← AANBEVOLEN**

Export genereert een `.json` bestand met alle tabellen:
```json
{
  "versie": "0.9",
  "export_tijdstip": "2026-03-22T10:00:00",
  "tabellen": {
    "locaties": [...],
    "teams": [...],
    "gebruikers": [...],
    "planning": [...],
    ...
  }
}
```

Import/merge leest dit JSON en doet per record:
- `INSERT ... ON CONFLICT (uuid) DO NOTHING` → standaard: skip duplicaten
- Of `ON CONFLICT (uuid) DO UPDATE` → optie: overschrijf met bron-data

Voordelen:
- Leesbaar, inspecteerbaar vóór import
- Selectieve merge mogelijk (bijv. alleen planning, niet gebruikers)
- Versiecontrole eenvoudig (weiger incompatibele versies)
- Werkt ook als pg_dump niet beschikbaar is in de app-container

**→ Aanbeveling: Optie B (JSON) voor merge, pg_dump custom format voor backup/restore**

---

## 3. Merge-logica per tabel

| Tabel | Conflict-sleutel | Standaard bij conflict |
|---|---|---|
| `locaties` | `uuid` | Skip (locaties wijzigen zelden) |
| `teams` | `uuid` | Skip |
| `gebruikers` | `uuid` | Skip (wachtwoord-hash nooit overschrijven!) |
| `gebruiker_rollen` | `(gebruiker_uuid, rol, scope_uuid)` | Skip |
| `shiftcodes` | `uuid` | Skip |
| `hr_regels` | `uuid` | Skip |
| `planning` | `uuid` | Skip |
| `verlof` | `uuid` | Skip |
| `notities` | `uuid` | Skip |
| `adv` | `uuid` | Skip |

**Openstaande vragen voor de gebruiker:**

1. **Wat merge je precies?** Wil je de volledige database samenvoegen (gebruikers, locaties, teams, planning, verlof allemaal), of enkel operationele data (planning + verlof)?
2. **Wat bij conflict?** Als dezelfde planning-regel (uuid) al bestaat maar met andere data (bijv. andere shift), wil je dan:
   - Skip (houd huidige)
   - Overschrijf (neem bron-data)
   - Rapporteer (toon conflictlijst voor manuele keuze)
3. **Meerdere instanties?** Is het de bedoeling dat bijv. twee locaties elk een eigen database hebben en je die periodiek samenvoegt? Of is dit eerder voor migratie/nood-restore?

---

## 4. Backup strategie

Gelijkaardig aan v0.7 maar aangepast voor PostgreSQL:

| Type | Frequentie | Bewaring | Trigger |
|---|---|---|---|
| Dagelijks | 1x per dag (bij opstart) | 30 dagen | App startup + APScheduler |
| Wekelijks | 1x per week | 12 weken | App startup + APScheduler |
| Maandelijks | 1x per maand | 12 maanden | App startup + APScheduler |
| Handmatig | Op aanvraag | Nooit automatisch verwijderd | GUI knop |
| Pre-restore | Voor elke restore/merge | 7 dagen | Automatisch |

**Opslag:** Docker volume `/backups` → via docker-compose gemount op NAS

**APScheduler** (reeds gebruikt in sommige v0.8 varianten) of simpelweg bij startup controleren.

---

## 5. GUI-scherm: `/beheer/database`

### Tabblad 1: Backups

```
[Maak handmatige backup]  [Ververs lijst]

Naam                              Grootte  Datum         Acties
────────────────────────────────────────────────────────────────
database_dagelijks_20260322.dump  12.4 MB  22/03/2026    [Download] [Restore]
database_dagelijks_20260321.dump  12.3 MB  21/03/2026    [Download] [Restore]
database_wekelijks_2026_W12.dump  12.1 MB  17/03/2026    [Download] [Restore]
...

Statistieken: 30 backups | Totaal: 370 MB
```

### Tabblad 2: Restore (import → overschrijven)

```
⚠️ WAARSCHUWING: Dit vervangt ALLE huidige data!

[Bestand kiezen: .dump]

Voor het uitvoeren wordt automatisch een pre-restore backup gemaakt.

[Restore uitvoeren]
```

### Tabblad 3: Merge (import → samenvoegen)

```
Laad een database-export (.json) van een andere instantie.
Bestaande records (op basis van UUID) worden overgeslagen.

[Bestand kiezen: .json]

Importeer:
☑ Locaties & Teams
☑ Gebruikers
☑ Planning
☑ Verlof
☑ HR-regels

[Voorvertoning]  →  [Merge uitvoeren]
```

**Voorvertoning** toont vóór uitvoering:
- X nieuwe records te importeren per tabel
- Y conflicten (al bestaande UUIDs) → worden overgeslagen
- Z records genegeerd (soft-deleted in bron)

---

## 6. Bestandsstructuur (nieuw)

```
backend/
  api/routers/
    beheer_database.py          ← nieuwe router (super_beheerder only)
  services/
    backup_service.py           ← pg_dump/pg_restore + scheduling
    database_export_service.py  ← JSON export (alle tabellen)
    database_import_service.py  ← JSON import + merge-logica
  templates/
    beheer/
      database.html             ← tabblad-UI
      database_voorvertoning.html ← merge preview
```

---

## 7. Docker aanpassingen

```yaml
# docker-compose.yml
volumes:
  - ./backups:/backups   # nieuw: backup volume

# Omgevingsvariabelen al aanwezig: DB_USER, DB_NAME, DB_HOST
```

De `pg_dump`/`pg_restore` binaries zijn beschikbaar in de PostgreSQL-image.
De app-container (Python) roept ze aan via `subprocess`.

---

## 8. Beveiliging

- Enkel `super_beheerder` heeft toegang (`vereiste_super_beheerder` dependency)
- Alle acties worden gelogd in `AuditLog`
- Upload-validatie: bestandstype, maximale grootte (configu reerbaar), versiecontrole
- Restore/merge vereist CSRF-token
- Pre-restore backup verplicht vóór elke destructieve actie

---

## 9. Prioriteit en fasering

**Fase 1 (basis):**
- Automatische backups via pg_dump bij startup
- Handmatige backup via GUI
- Lijst + download van backups
- Restore (overschrijven)

**Fase 2 (merge):**
- JSON export
- JSON import met merge-logica
- Voorvertoning scherm

---

## Openstaande beslissingen (vóór implementatie)

1. **Merge-scope:** Alles of selectief? (zie §3)
2. **Conflict-strategie:** Skip / Overschrijf / Rapporteer?
3. **Backup-formaat voor merge:** JSON (aanbevolen) of pg_dump?
4. **APScheduler** voor geplande backups of enkel bij startup controleren?
5. **Max upload-grootte:** Standaard 100 MB? (configureerbaar via Instellingen)
