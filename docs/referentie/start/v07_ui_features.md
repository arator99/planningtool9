# v0.7 UI Features — Referentiedocument

Per scherm: naam, v0.8 URL, aanwezige UI-elementen (filters, knoppen, kolommen, statusinfo).
Gebruik dit document bij elke nieuwe v0.8 implementatie om UI-pariteit te garanderen.

---

## Gebruikers lijst
**v0.8 URL:** `/beheer/gebruikers`
**Rollen:** beheerder, planner

### Filters (bovenaan de lijst)
- Zoekbalk op volledige naam en gebruikersnaam
- Rol-dropdown: Alle rollen / beheerder / planner / hr / medewerker
- Status-dropdown: Actief / Inactief / Alle

### Tabel kolommen
| Kolom | Beschrijving |
|-------|-------------|
| Naam | volledige_naam of gebruikersnaam |
| Gebruikersnaam | gebruikersnaam |
| Rol | badge (kleur per rol) |
| 2FA | Actief / — |
| Status | Actief / Inactief |
| Acties | Bewerk · Wachtwoord · Deactiveer/Activeer |

### Footer
- Totaal actieve medewerkers in groep (bijv. "12 actieve medewerkers")

---

## Verlof aanvragen lijst
**v0.8 URL:** `/verlof`
**Rollen:** alle (medewerker ziet eigen aanvragen, behandelaar ziet alle)

### Filters (tabs bovenaan)
- **Alle** (telt alle aanvragen)
- **In behandeling** (pending, met teller)
- **Goedgekeurd** (met teller)
- **Geweigerd** (met teller)

### Tabel kolommen (behandelaar)
| Kolom | Beschrijving |
|-------|-------------|
| Medewerker | naam + "(door planner)" indien namens ingediend |
| Periode | start – eind |
| Dagen | aantal_dagen |
| Opmerking | inkortbaar |
| Status | badge (geel/groen/rood) |
| Behandeld | datum + reden weigering |
| Acties | Goedkeuren · Weigeren (enkel bij pending) |

### Bulk acties (behandelaar)
- Checkboxes op pending-rijen
- "Selecteer alles" checkbox in header
- "Bulk goedkeuren" knop voor alle geselecteerde pending aanvragen

### Header knoppen (behandelaar)
- Maand overzicht (link naar `/verlof/overzicht`)
- Saldo beheer (link naar `/verlof/saldo`)
- + Nieuwe aanvraag

---

## Verlof maandoverzicht grid
**v0.8 URL:** `/verlof/overzicht`
**Rollen:** beheerder, planner, hr

### Grid
- Maandgrid: rijen = medewerkers, kolommen = datums
- Cel kleuren: pending=geel, goedgekeurd=groen, leeg=transparant
- Capaciteitsrij onderaan: totaal medewerkers − goedgekeurd afwezig per dag

### Navigatie
- Vorige / volgende maand navigatie
- Huidige maand + jaar als titel

---

## Notities
**v0.8 URL:** `/notities`
**Rollen:** alle

### Tabs
- Inbox (met ongelezen teller)
- Verzonden

### Inbox filter (dropdown naast tabs)
- Alle
- Ongelezen
- Hoog (prioriteit)

### Inbox items
- Prioriteit-indicator (oranje dot = hoog, blauw = normaal, grijs = laag)
- Afzender naam
- Groepsbadge als naar iedereen
- Hoog-badge
- Timestamp
- Bericht tekst
- Markeer als gelezen knop (indien ongelezen)

---

## Shiftcodes lijst
**v0.8 URL:** `/shiftcodes`
**Rollen:** beheerder, planner

### Zoekbalk
- Client-side filter op code en naam
- Filtert over alle categorieën, verbergt lege categorieën

### Groepering
- Gesorteerd per categorie (vroeg / laat / nacht / dag / rust / overig)
- Categorie-header met achtergrondkleur en telling

### Tabel kolommen per categorie
| Kolom | Beschrijving |
|-------|-------------|
| Code | vetgedrukt |
| Tijden | start – eind |
| Dagtype | dag_type |
| Werkpost | gekoppelde werkpost of — |
| Kritisch | ja/— badge |
| Acties | Bewerk · Verwijder (alleen beheerder) |

---

## Werkposten lijst
**v0.8 URL:** `/werkposten`
**Rollen:** beheerder, planner

### Zoekbalk
- Client-side filter op naam

### Tabel kolommen
| Kolom | Beschrijving |
|-------|-------------|
| Naam | werkpost naam |
| Beschrijving | omschrijving of — |
| Telt als werkdag | ✓/— |
| Reset 12u rust | ✓/— |
| Actief | badge |
| Acties | Bewerk · Deactiveer/Activeer |

---

## Planning maandgrid
**v0.8 URL:** `/planning`
**Rollen:** beheerder, planner

### Toolbar
- Maand/jaar navigatie
- Valideer knop → foutenpaneel (HTMX)
- Concept/Publiceer knop
- Batch auto-invullen knop

### Grid
- Rijen = medewerkers, kolommen = datums
- Cel klik → shiftcode HUD + suggestie paneel
- Cel kleur per shift_type
- Cel-markeringen per HR-validatie (rood/oranje/geel rand)
- Lege cel met "Auto" knop voor suggestie

### Validatiepaneel (HTMX fragment)
- Lijst van HR-overtredingen per ernst (CRITICAL eerst)
- Override knop bij CRITICAL overtredingen

---

## HR Regels lijst
**v0.8 URL:** `/hr`
**Rollen:** beheerder, planner

### Tabel kolommen
| Kolom | Beschrijving |
|-------|-------------|
| Regel | HR code |
| Ernst | CRITICAL/WARNING/INFO badge |
| Waarde | drempelwaarde |
| Rode lijn | interval configuratie |
| Acties | Bewerk |

---

## Rapporten
**v0.8 URL:** `/rapporten`
**Rollen:** beheerder, planner, hr

### Secties
1. **Maandgrid** — read-only planning view + CSV download
2. **Verlofoverzicht** — per medewerker samenvatting + CSV
3. **Balans** — zaterdagen/zondagen/feestdagen schuld/compensatie

---

## Dashboard
**v0.8 URL:** `/`
**Rollen:** alle

### Tegels (per rol zichtbaar)
| Tegel | Zichtbaar voor |
|-------|---------------|
| Planning | beheerder, planner |
| Verlof | alle |
| Gebruikers | beheerder, planner |
| Shiftcodes | beheerder, planner |
| HR Regels | beheerder, planner |
| Rapporten | beheerder, planner, hr |
| Notities | alle |
| Instellingen | beheerder |

---

## Verlof saldo beheer
**v0.8 URL:** `/verlof/saldo`
**Rollen:** beheerder, planner, hr

### Tabel kolommen
| Kolom | Beschrijving |
|-------|-------------|
| Medewerker | naam |
| VV recht | vakantieverlof recht |
| VV overgedragen | vorig jaar overgedragen |
| VV opgenomen | dit jaar opgenomen |
| VV resterend | berekend resterend |
| KD recht | compensatiedag recht |
| KD resterend | berekend resterend |
| Acties | Aanpassen |

### Acties
- Jaar overdracht (VV + KD restanten overbrengen naar volgend jaar)
- 1-mei verval (overgedragen VV-dagen op 0 zetten)

---

## Competenties lijst
**v0.8 URL:** `/beheer/competenties`
**Rollen:** beheerder, planner

### Tabel kolommen
| Kolom | Beschrijving |
|-------|-------------|
| Naam | competentie naam |
| Beschrijving | omschrijving |
| Categorie | categorie |
| Actief | badge |
| Acties | Bewerk · Deactiveer |

---

## Changelog
**v0.8 URL:** `/changelog`
**Rollen:** alle (read-only)

---

## Notities voor nieuwe feature-implementaties

1. **Zoekbalk**: standaard client-side JS filter (tabel klein genoeg). Server-side bij > 200 rijen.
2. **Status-tabs**: altijd met tellers (hoeveel per status).
3. **Footer statistieken**: toon totalen ongeacht actieve filters.
4. **Bulk acties**: via JS + hidden form (CSRF token verplicht).
5. **Maand navigatie**: altijd vorige/volgende pijl + huidige maand/jaar als titel.
