# Architectuur Voorstel: Organisatiestructuur v0.9

## 1. Het Drie-Domein Principe (Herhaald)

1.  **ORGANISATIE**: De hiërarchische boom (Locatie, Team, Area). Kent de andere domeinen niet.
2.  **AUTORISATIE**: Koppelt Gebruikers aan de Organisatie via Rollen.
3.  **OPERATIE**: De dagelijkse data (Planning, Verlof, Notities). Verwijst naar Organisatie, nooit direct naar Autorisatie.

---

## 2. Domein 1: De Organisatiehiërarchie

De structuur is opgebouwd van Nationaal naar Team-niveau.

-   **Nationaal**: Hoogste niveau (Superbeheerder).
-   **Area**: Groepering van locaties voor HR-overzicht (bijv. 5 Area's).
-   **Locatie**: Het fysieke beheerniveau (bijv. Antwerpen, Hasselt).
-   **Team**: De kleinste eenheid waar de planning op gebeurt (bijv. Permanentie, Traffic).

                                           [ NATIONAAL ]  
                                                        │  
                           ┌──────────┴──────────┐  
             (Superbeheerder)                   (National HR) <── Ziet alles (Read-only)  
                           │  
           ┌─────┴──────────────┐  
[ AREA A ]                                         [ AREA B ]  
    │                                                           │  
  (Area HR A) <──┐                       (Area HR B) <── Ziet enkel Area B  
           │                │                                  │  
┌───┴───┐      │                        ┌───┴───┐  
[LOC 1]    [LOC 2]  └─────      [LOC 3]       [LOC 4]  
  │                 │                                │                   │  
(Beheerder) (Beheer)               (Beheer)          (Beheer)  
  │                 │                                 │                   │  
[TEAMS] [TEAMS]                    [TEAMS]         [TEAMS]  
  │                  │                                │                   │  
(Plan)          (Plan)                         (Plan)             (Plan)  
  │                  │                                  │                   │  
  └───────┴──────┬──────┴───────┘  
                │  
          [ MEDEWERKER ]  
          (Lidmaatschap)

---

## 3. Domein 2: Autorisatie & Lidmaatschap

Om flexibiliteit te bieden (zoals werknemers die op meerdere locaties werken), ontkoppelen we de `Gebruiker` van een vaste `Locatie`.

### De Koppeltabel: `Lidmaatschap`

Dit is de "lijm" tussen de Gebruiker en de Organisatie.

Veld

Type

Beschrijving

`gebruiker_id`

FK

Verwijst naar de unieke mens.

`team_id`

FK

Verwijst naar het team.

`type`

Enum

`Vast`, `Reserve`, `Detachering`.

`is_planner`

Bool

Geeft schrijfrechten op dit specifieke team.

`percentage`

Int

Optioneel: bijv. 50% voor halftijdse verdeling.

### Rollen op basis van Scope

-   **Superbeheerder**: Toegang tot alles (Nationaal).
-   **HR**: View-only op basis van `Area_ID`.
-   **Beheerder**: Schrijfrechten op `Locatie_ID` (instellingen, nieuwe teams).
-   **Planner**: Schrijfrechten op `Team_ID` (alleen waar `is_planner=True`).
-   **Werknemer**: View-only op eigen data en team-planning.

---

## 4. Domein 3: Operaties & De "Rode Lijn"

Door de ontkoppeling van gebruikers werkt de logica nu als volgt:

-   **Planning-validatie**: De "Rode Lijn" (70.000 regels logica) kijkt niet meer naar de team-limiet, maar naar de **Gebruiker-limiet**.  
        - *Scenario:* Als Jan in Antwerpen is ingepland, ziet de planner in Hasselt direct een conflict in de Rode Lijn omdat de query checkt: `SELECT * FROM planning WHERE gebruiker_id = Jan`.
-   **Notities & Mailbox**: Notities worden gepost naar een `Team_ID` of `Locatie_ID`. Planners zien automatisch alle notities van de teams waar zij het label `is_planner` hebben.

---

## 5. Implementatie-richtlijnen (Database)

1.  **Verwijder `locatie_id` uit de `Gebruiker`-tabel.** Een gebruiker "is" niemand, hij "werkt voor" een team.
2.  **Context-validatie**: Elke API-call in FastAPI moet de `current_user` valideren tegen de gevraagde `team_id` of `locatie_id` via de `Lidmaatschap`-tabel.
3.  **Audit Logging**: Sla bij elke wijziging niet alleen de `gebruiker_id` op, maar ook de `locatie_id` waar de actie plaatsvond voor snelle filtering door HR.

## 6. Architectuur: Overerving & Lidmaatschap (v0.9)

In v0.9 stappen we volledig af van de starre `gebruiker.locatie_id` structuur. We implementeren een systeem gebaseerd op **Inheritance (Overerving)** om maximale flexibiliteit en zuivere data-integriteit te garanderen.

### A. De 'Single Source of Truth': De Lidmaatschapstabel  
We vervangen de versnipperde rollen door één centrale koppeltabel die Gebruikers aan de Organisatie verbindt.

* **Tabel:** `Lidmaatschap` (voorheen `GebruikerRol`)  
* **Velden:** * `gebruiker_id` (FK)  
    * `team_id` (FK)  
    * `is_planner` (Boolean) — *De enige bron voor planningsrechten.*  
    * `type` (Enum: Vast, Reserve, Detachering)  
* **Geen Locatie-ID in Gebruiker:** De `Gebruiker`-tabel bevat geen `locatie_id`. Een gebruiker "is" geen locatie, maar "werkt voor" teams.

### B. Locatie via Overerving (Inheritance)  
De locatie-context van een gebruiker wordt in v0.9 dynamisch **afgeleid**:  
1.  **Systeem-logica:** `Gebruiker` → `Lidmaatschap` → `Team` → `Locatie`.  
2.  **Multi-locatie support:** Als een gebruiker lid is van Team A (Antwerpen) en Team B (Hasselt), erft hij beide contexten.  
3.  **UI/UX:** Bij het inloggen ziet de gebruiker data van beide locaties, of krijgt hij een snelle 'locatie-switcher' op basis van zijn actieve lidmaatschappen.

### C. Gedifferentieerde Schrijfrechten  
Rechten worden niet meer binair (lezen of schrijven) bepaald, maar op **Object-niveau**:  
* **Planning-Objecten:** Alleen schrijfbaar als `is_planner=True` voor dat specifieke `team_id`.  
* **Self-Service Objecten:** Een 'Werknemer' heeft altijd schrijfrechten op zijn *eigen* entiteiten (Verlof aanvragen, Notities sturen naar zijn eigen planner).  
* **Beheer-Objecten:** Alleen schrijfbaar door de rol `Beheerder` op basis van de overgeërfde `locatie_id`.

### D. 'Clean Slate' Migratie (v0.7 → v0.9)  
Omdat we vertrekken vanuit een v0.7 database met slechts 15 gebruikers, saneren we alle legacy tijdens de import:  
* **Extract:** Haal data uit v0.7 SQLite (waar locatie nog niet bestond).  
* **Transform:** Map de oude bestandsstructuur direct naar de nieuwe `Team` + `Locatie` hiërarchie.  
* **Load:** Vul de `Lidmaatschap`-tabel direct correct in. Hiermee voorkomen we dat v0.8-fouten (zoals de dubbele teamlid/planner records) de v0.9 database vervuilen.

## 7. Migratieplan (v0.7 naar v0.9)

We hanteren een 'Clean Data, New Structure' aanpak voor de migratie van de huidige 15 gebruikers en historische planning.

1. **Data Extractie**: Data wordt uit de v0.7 SQLite bestanden (`.db`) getrokken.  
2. **Structural Mapping**:  
    - Oude 'Files' worden gemapt naar nieuwe `Team_ID`'s.  
    - Oude 'Rollen' worden vertaald naar de `is_planner` boolean in de `Lidmaatschap`-tabel.  
3. **Locatie-overerving**: Tijdens import wordt de historische data gekoppeld aan teams. De locatie-context wordt automatisch verkregen via de `Team -> Locatie` relatie.  
4. **Geen Legacy**: De `Gebruiker`-tabel in v0.9 bevat GEEN `locatie_id`. Alle scoping gebeurt via de lidmaatschappen.