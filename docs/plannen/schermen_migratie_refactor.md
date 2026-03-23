# Schermen migreren naar nieuwe organisatiestructuur + nieuwe stijl

## Context

Na de `organisatiestructuur_refactor` zijn models en services grotendeels up-to-date, maar routers en templates zijn deels gebouwd rond de oude structuur. Daarnaast is een nieuwe Figma-stijl geïntroduceerd op het dashboard en de navigatiebalk, die nu als standaard geldt voor alle schermen.

**Strategie: bestaande schermen hergebruiken en gericht fixen** — niet herbouwen. Elk scherm krijgt een audit op drie assen:
1. Code-correctheid (nieuwe rolstructuur)
2. GUI-bruikbaarheid (locatiecontext zichtbaar, teamlidmaatschappen getoond)
3. Visuele stijl (Figma-design overnemen)

---

## Oud vs. nieuw — verboden codepatronen

| Oud (verboden) | Nieuw (verplicht) |
|---|---|
| `GebruikerRol.scope_id` | `scope_locatie_id` / `scope_area_id` |
| `rol='teamlid'` of `rol='planner'` in GebruikerRol | `Lidmaatschap.is_planner` / `Lidmaatschap.type` |
| `Gebruiker.locatie_id` | `haal_actieve_locatie_id()` of Lidmaatschap → Team → Locatie |
| `heeft_rol_in_team(..., ("teamlid","planner"), ...)` | check op `Lidmaatschap` |
| `is_reserve` vlag | `Lidmaatschap.type == LidmaatschapType.reserve` |

---

## Nieuwe stijlstandaard (Figma-design)

Geïntroduceerd op dashboard + nav. Overal over te nemen:

### Widgets / stat-kaarten
```html
<!-- Patroon: icoon op gekleurde achtergrond, grotere padding -->
<div class="flex items-center gap-4 p-5 rounded-2xl border transition-all hover:shadow-md hover:-translate-y-0.5"
     style="background: var(--achtergrond-widget); border-color: var(--rand);">
    <div class="flex-shrink-0 w-14 h-14 rounded-2xl flex items-center justify-center"
         style="background: var(--tegel-planning);">
        {# wit SVG-icoon w-7 h-7 #}
    </div>
    ...
</div>
```

### Moduletegels
```html
<!-- rounded-2xl, icoon w-12 h-12 met var(--tegel-*) achtergrond -->
<div class="rounded-2xl shadow-sm border p-5 hover:shadow-md hover:-translate-y-0.5 transition-all"
     style="background: var(--achtergrond-widget); border-color: var(--rand);">
    <div class="inline-flex items-center justify-center w-12 h-12 rounded-2xl mb-4"
         style="background: var(--tegel-planning);">
        {# wit SVG-icoon w-6 h-6 #}
    </div>
    ...
</div>
```

### Icoon-kleuren — CSS variabelen (nooit hardcoded hex)
```css
/* Beschikbaar via var(--tegel-*) */
--tegel-planning, --tegel-verlof, --tegel-gebruikers, --tegel-shiftcodes,
--tegel-hr, --tegel-rapporten, --tegel-notities, --tegel-instellingen,
--tegel-locaties, --tegel-hr-nationaal, --tegel-database

/* Beschikbaar via var(--rol-*) */
--rol-super, --rol-beheerder, --rol-planner, --rol-hr
```

### Knoppen en actieve states
```html
<!-- Primaire actie-knop -->
<button class="px-4 py-2 rounded-xl text-sm font-semibold text-white transition-colors hover:opacity-90"
        style="background: var(--primair);">

<!-- Pill active state (nav, tabs) -->
style="background: var(--primair); color: #ffffff;"

<!-- Secundaire / ghost knop -->
<button class="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
        style="background: var(--hover-bg); color: var(--tekst);">
```

### Kaarten / containers
```html
<!-- Standaard kaart -->
<div class="rounded-2xl border p-5"
     style="background: var(--achtergrond-widget); border-color: var(--rand);">

<!-- Subtiel (binnen een kaart) -->
<div class="rounded-xl p-4"
     style="background: var(--hover-bg);">
```

### Badges / labels
```html
<!-- Status badge — gebruik semantische kleuren, geen hardcoded Tailwind -->
<span class="text-xs font-medium px-2.5 py-1 rounded-full bg-orange-100 text-orange-700">
<!-- Of via CSS variabelen voor custom statussen -->
<span style="background: var(--msg-waarschuwing-bg); color: var(--waarschuwing);">
```

---

## Checklist per scherm (drie assen)

### As 1 — Code-correctheid
- [ ] Geen `rol in ('teamlid', 'planner')` in router of template
- [ ] Geen `scope_id` — alleen `scope_locatie_id` / `scope_area_id`
- [ ] Geen `gebruiker.locatie_id`
- [ ] Locatiegebonden queries via `BaseRepository._locatie_filter()` of `actieve_locatie_id`
- [ ] `heeft_rol_in_team()` / `heeft_rol_in_locatie()` i.p.v. raw GebruikerRol query

### As 2 — GUI-bruikbaarheid
- [ ] Locatiecontext zichtbaar op het scherm zelf (niet alleen in navbar)
- [ ] Teamlidmaatschap getoond waar relevant
- [ ] Rolweergave klopt met nieuwe structuur (admin-rollen + lidmaatschappen apart)
- [ ] Area zichtbaar/beheerbaar waar relevant

### As 3 — Visuele stijl
- [ ] Kaarten: `rounded-2xl` i.p.v. `rounded-xl` of `rounded-lg`
- [ ] Iconen op gekleurde achtergrond: `var(--tegel-*)` i.p.v. `bg-*-100 text-*-600`
- [ ] Geen hardcoded hex-kleuren — altijd `var(--...)` of semantische Tailwind-klassen
- [ ] Knoppen: juist patroon (primair / ghost / gevaar)
- [ ] Hover-states: `-translate-y-0.5 shadow-md` op klikbare kaarten

---

## Nieuw te bouwen (ontbreekt volledig)

### Area-beheer
- [ ] `backend/api/routers/beheer_areas.py` — CRUD (super_beheerder only)
- [ ] `backend/templates/pages/beheer/areas/lijst.html`
- [ ] `backend/templates/pages/beheer/areas/formulier.html`
- [ ] Registreer in `backend/main.py`
- [ ] Voeg toe aan Nationaal Beheer dropdown in nav

---

## Screenaudit per scherm

### ✅ Al gedaan
- **Dashboard** — nieuwe stijl, correcte planner-checks
- **Navigatiebalk** (app.html) — logo, pill active states, h-16, CTA account-knop
- **planning.py** — `vereiste_planner_of_hoger` i.p.v. `vereiste_rol("beheerder","planner")`
- **sjablonen.py** — `heeft_rol('planner')` checkt nu Lidmaatschap

---

### 1. Gebruikers — ROOD + stijl

**Router** `backend/api/routers/gebruikers.py`
- [ ] Verwijder `'planner'`/`'teamlid'` uit rolfilter-opties
- [ ] Voeg `areas` dict toe aan template-context
- [ ] Verwijder `is_reserve` Form-param

**Template** `backend/templates/pages/gebruikers/lijst.html`
- [ ] Vervang `scope_id` → `scope_locatie_id` / `scope_area_id`
- [ ] Verwijder `'teamlid'`/`'planner'` uit rol-badges
- [ ] Aparte sectie voor teamlidmaatschappen (via `g.lidmaatschappen`)
- [ ] Planner-badge via `lid.is_planner`
- [ ] Stijl: kaarten naar `rounded-2xl`, icoon-badges naar `var(--tegel-*)`

**Template** `backend/templates/pages/gebruikers/formulier.html`
- [ ] Verwijder `<option value="teamlid">` en `<option value="planner">`
- [ ] Verwijder `is_reserve` checkbox
- [ ] Stijl: formulier naar nieuwe stijlstandaard

---

### 2. Planning — ROOD + stijl

**Router** `backend/api/routers/planning.py` ✅ al gefixed

**Templates** `backend/templates/pages/planning/`
- [ ] Locatiecontext zichtbaar op maandgrid
- [ ] Stijl: header, knoppen, badges naar nieuwe standaard

---

### 3. Notities — ROOD

**Router** `backend/api/routers/notities.py`
- [ ] `_haal_rollen()` vervangen door Lidmaatschap/team-context

**Template** `backend/templates/pages/notities/lijst.html`
- [ ] Verboden patronen?
- [ ] Stijl: kaarten, badges

---

### 4. Teams — ORANJE + stijl

**Router** `backend/api/routers/teams.py`
- [ ] Audit log: `doel_type="Lidmaatschap"` i.p.v. `"GebruikerRol"`

**Templates** `backend/templates/pages/teams/`
- [ ] Locatienaam zichtbaar bovenaan lijst
- [ ] Stijl: kaarten, leden-badges, knoppen

---

### 5. Verlof — ORANJE + stijl

- [ ] Scope-gebruik controleren
- [ ] Stijl: status-badges, kaarten, knoppen

---

### 6. Dashboard-gerelateerde schermen — stijl

- [ ] `verlof/saldo` — stat-kaarten naar nieuwe stijl
- [ ] `verlof/overzicht` — grid/kaarten
- [ ] `adv/lijst` — kaarten

---

### 7. Rapporten — ORANJE + stijl

- [ ] Verboden patronen?
- [ ] Stijl: kaartcontainers, knoppen, filters

---

### 8. HR + Beheer HR — ORANJE + stijl

- [ ] Area-scope correct?
- [ ] Stijl: formulieren, overzichtskaarten

---

### 9. Locaties + Area-beheer — ORANJE + nieuw

- [ ] Area-beheer bouwen (zie boven)
- [ ] Locatielijst: stijl naar nieuwe standaard

---

### 10. Beheer-schermen — stijl

- [ ] `teams` (al deels gedaan in #4)
- [ ] `competenties`, `typetabellen`, `werkposten`, `shiftcodes`
- [ ] `logboek`, `scherm_rechten`
- [ ] `instellingen`

---

### 11. Overige schermen — groen + stijl

- [ ] `aankondigingen`
- [ ] `account` (wachtwoord, voorkeuren)
- [ ] `help/changelog`

---

## Groepen-templates

- [ ] `backend/templates/pages/groepen/` — controleren of actief; zo niet: verwijderen

---

## Migratiescript

- [ ] `backend/migrations/versions/010_lidmaatschap_area_refactor.py` — data-mapping verifiëren

---

## Werkwijze per scherm

1. Lees router + alle bijbehorende templates
2. Voer drie-as checklist uit (code / GUI / stijl)
3. Fix gericht — minimale aanpassingen, geen herbouw
4. Vink af in dit plan

---

## Verificatie na elke fix

- `docker compose build app && docker compose up -d` (CSS rebuild nodig na input.css wijzigingen)
- Open scherm als super_beheerder én als planner én als gewone medewerker
- Geen 500-fouten, data correct, locatiecontext zichtbaar
- Geen `AttributeError: 'GebruikerRol' object has no attribute 'scope_id'` in logs
- Visueel: iconen op gekleurde achtergrond, rounded-2xl kaarten, geen hardcoded kleuren
