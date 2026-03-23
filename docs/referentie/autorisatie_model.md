# Referentie: Autorisatiemodel (v0.9)

**Geldig vanaf:** organisatiestructuur refactor (zie `docs/plannen/organisatiestructuur_refactor.md`)

---

## Twee tabellen, twee verantwoordelijkheden

Het autorisatiemodel is verdeeld over twee tabellen met een strikte scheiding van verantwoordelijkheden:

| Tabel | Verantwoordelijkheid | Rollen |
|---|---|---|
| `Lidmaatschap` | Operationeel — wie werkt in welk team | teamlid, planner (`is_planner=True`) |
| `GebruikerRol` | Administratief — wie beheert welke locatie/area | beheerder, hr, super_beheerder |

**Vuistregel:** Als de vraag gaat over *planning en teamwerk* → `Lidmaatschap`. Als de vraag gaat over *beheer en instellingen* → `GebruikerRol`.

---

## Lidmaatschap — teamlid en planner

Een `Lidmaatschap` koppelt een gebruiker aan een team. De `is_planner` boolean op datzelfde record bepaalt of die persoon schrijfrechten heeft op de planning van dat team.

```
Lidmaatschap
├── gebruiker_id    FK → Gebruiker
├── team_id         FK → Team          (echte DB-constraint)
├── is_planner      bool               False = teamlid, True = planner
├── type            Vast | Reserve | Detachering
└── is_actief       bool
```

**Één record per persoon per team** — niet twee. Een planner is geen apart roltype maar een attribuut van het lidmaatschap.

### Voorbeelden

```
Jan in Team Permanentie, gewone medewerker:
  → Lidmaatschap(team_id=Permanentie, is_planner=False, type=Vast)

Ann in Team Permanentie, plant het team:
  → Lidmaatschap(team_id=Permanentie, is_planner=True, type=Vast)

Pieter in twee teams:
  → Lidmaatschap(team_id=Permanentie, is_planner=False, type=Vast)
  → Lidmaatschap(team_id=Traffic, is_planner=False, type=Detachering)
```

---

## GebruikerRol — beheerder, HR, super_beheerder

`GebruikerRol` is uitsluitend voor administratieve rollen met een expliciete locatie- of area-scope.
Geen polymorfische `scope_id` — elke rol heeft zijn eigen getypeerde FK.

```
GebruikerRol
├── gebruiker_id       FK → Gebruiker
├── rol                beheerder | hr | super_beheerder
├── scope_locatie_id   FK → Locatie (nullable) — gebruikt door: beheerder
├── scope_area_id      FK → Area    (nullable) — gebruikt door: hr
└── is_actief          bool
```

| Rol | scope_locatie_id | scope_area_id |
|---|---|---|
| `beheerder` | locatie_id | NULL |
| `hr` | NULL | area_id |
| `super_beheerder` | NULL | NULL |

**`super_beheerder` heeft geen scope** — ziet alles zonder filter.

### Voorbeelden

```
Marc beheert locatie Antwerpen:
  → GebruikerRol(rol='beheerder', scope_locatie_id=Antwerpen, scope_area_id=NULL)

Sara is HR voor Area West:
  → GebruikerRol(rol='hr', scope_locatie_id=NULL, scope_area_id=Area_West)

Thomas is super_beheerder:
  → GebruikerRol(rol='super_beheerder', scope_locatie_id=NULL, scope_area_id=NULL)
```

---

## Combinatie van rollen

Een persoon kan tegelijk een `GebruikerRol` én een `Lidmaatschap` hebben. Dat zijn verschillende verantwoordelijkheden in verschillende tabellen — geen architectuurprobleem.

```
Marc beheert locatie Antwerpen én plant Team Permanentie:
  → GebruikerRol(rol='beheerder', scope_locatie_id=Antwerpen)
  → Lidmaatschap(team_id=Permanentie, is_planner=True)
```

De authorization-checks raken elk hun eigen tabel:

```python
# Mag Marc de locatie-instellingen wijzigen?
heeft_rol_in_locatie(marc.id, antwerpen_id, ("beheerder",), db)   # → GebruikerRol

# Mag Marc de planning van Permanentie schrijven?
heeft_rol_in_team(marc.id, permanentie_id, is_planner=True, db)   # → Lidmaatschap
```

---

## Invariant: elke gebruiker heeft minstens één lidmaatschap

Omdat de locatie-context afgeleid wordt via `Lidmaatschap → Team → Locatie`, moet elke gebruiker
**altijd minstens één actief lidmaatschap** hebben. Een gebruiker zonder lidmaatschap heeft geen
locatie en kan de app niet gebruiken.

**Handhaving:**
- `GebruikerService.maak_gebruiker_aan()` vereist een `team_id` als parameter en maakt het
  lidmaatschap in dezelfde transactie aan. Los aanmaken is niet mogelijk via de service.
- Admin-UI voor gebruikersbeheer toont teamkeuze als verplicht veld bij aanmaken.
- Bij soft-delete van een lidmaatschap: service controleert of er nog minstens één actief
  lidmaatschap overblijft. Zo niet → weiger de verwijdering met een foutmelding.

---

## Locatie-context en de switcher

Omdat een gebruiker via lidmaatschappen op meerdere locaties actief kan zijn, wordt de
actieve locatie bepaald via `haal_actieve_locatie_id()` in `api/dependencies.py`.

**Hoe de actieve locatie bepaald wordt (per rol):**

| Rol | Bron |
|---|---|
| teamlid / planner | `Lidmaatschap → Team → locatie_id` |
| beheerder | `GebruikerRol.scope_locatie_id` |
| hr | cookie, beperkt tot locaties in `GebruikerRol.scope_area_id` |
| super_beheerder | cookie, geen beperking |

**Cookie `locatie_context`:** bij meerdere beschikbare locaties wordt de actieve locatie
opgeslagen in een cookie. Een locatie-switcher in de navigatiebalk laat de gebruiker wisselen
tussen hun beschikbare locaties. Enkel zichtbaar als de gebruiker > 1 locatie heeft.

`BaseRepository` ontvangt altijd `locatie_id: int | None` — de interface is ongewijzigd.
`None` = super_beheerder zonder filter.

---

## Authorization checks — welke functie voor welke check

```python
# Zit deze gebruiker in dit team? (teamlid of planner)
heeft_lid_van_team(gebruiker_id, team_id, db) -> bool
# → Lidmaatschap waar team_id=team_id AND is_actief=True

# Heeft deze gebruiker plannerrechten op dit team?
heeft_rol_in_team(gebruiker_id, team_id, is_planner=True, db) -> bool
# → Lidmaatschap waar team_id=team_id AND is_planner=True AND is_actief=True

# Heeft deze gebruiker een admin-rol op deze locatie?
heeft_rol_in_locatie(gebruiker_id, locatie_id, ("beheerder",), db) -> bool
# → GebruikerRol waar scope_locatie_id=locatie_id AND rol IN (...) AND is_actief=True

# Heeft deze gebruiker HR-rechten op deze area?
heeft_rol_in_area(gebruiker_id, area_id, ("hr",), db) -> bool
# → GebruikerRol waar scope_area_id=area_id AND rol IN (...) AND is_actief=True

# Alle teams waar deze gebruiker planner is
haal_planner_team_ids(gebruiker_id, db) -> list[int]
# → Lidmaatschap waar is_planner=True AND is_actief=True
```

---

## Organisatiehiërarchie

```
Nationaal
    └── Area  (bijv. Area West, Area Oost)
            └── Locatie  (bijv. Antwerpen, Hasselt)
                    └── Team  (bijv. Permanentie, Traffic)
                            └── Lidmaatschap  (koppelt Gebruiker aan Team)
```

- `Locatie.area_id` → FK naar Area
- `Team.locatie_id` → FK naar Locatie
- `Lidmaatschap.team_id` → FK naar Team
- `GebruikerRol.scope_locatie_id` → FK naar Locatie (voor beheerder)
- `GebruikerRol.scope_area_id` → FK naar Area (voor hr)
