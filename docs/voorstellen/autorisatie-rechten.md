# Blueprint: Autorisatie, Rollen en Rechten (v0.9)

**Status:** Definitief Ontwerp  
**Datum:** 2026-03-23  
**Focus:** Eliminatie van legacy v0.8 permissie-bugs en implementatie van Planner-autonomie.

---

## 1. Kernprincipe: Overerving (Inheritance)

In v0.9 stappen we volledig af van een vaste `locatie_id` in het gebruikersprofiel. De context van een gebruiker wordt bepaald door zijn actieve koppelingen.

* **De Keten:** `Gebruiker` → `Lidmaatschap` → `Team` → `Locatie` → `Area`.  
* **Unieke Identificatie:** De `gebruikersnaam` is uniek binnen de gehele nationale organisatie. Dit is de primaire sleutel voor het zoeken en koppelen van personeel over locaties heen.

---

## 2. De Lidmaatschapstabel (De 'Lijm')

Deze tabel vervangt de oude `GebruikerRol` en lost de "Planner-duabiliteit" op (iemand die zowel lid als planner is).

| Veld | Type | Beschrijving |  
| :--- | :--- | :--- |  
| `gebruiker_id` | FK | Koppeling naar de unieke Gebruiker. |  
| `team_id` | FK | Koppeling naar het specifieke Team. |  
| `is_planner` | Boolean | **True**: Mag de planning van dit team beheren. **False**: Regulier teamlid. |  
| `type` | Enum | `Vast`, `Reserve`, `Detachering`. |  
| `percentage` | Int | Contractuele verdeling (bijv. 50 voor halftijds). |

---

## 3. Rechtenmatrix per Rol

Rechten worden afgedwongen op **Object-niveau** binnen de toegewezen scope.

| Rol | Niveau (Scope) | Personeelsbeheer | Planning (Shifts) | Verlof & Notities |  
| :--- | :--- | :--- | :--- | :--- |  
| **Superbeheerder** | Nationaal | Full Access | Full Access | Full Access |  
| **National HR** | Nationaal | Read-Only (Audit) | Read-Only | Read-Only |  
| **Area HR** | Area | Read-Only (Area) | Read-Only | Read-Only |  
| **Beheerder** | Locatie | Full Admin (Locatie) | Read-Only (Audit) | Read/Write (Locatie) |  
| **Planner** | Team | **Team-beheer (Lidmaatschap)** | **Read/Write (Team)** | Read/Write (Team) |  
| **Werknemer** | Gebruiker | Geen | Read (Team) | **Read/Write (Eigen)** |

---

## 4. Planner Autonomie: Het "Zoek-en-Koppel" Systeem

Om centrale beheerders (bijv. op grote locaties als Antwerpen) te ontlasten, krijgt de Planner beheerrechten over het eigen team:

1.  **Gebruiker Zoeken:** Planners kunnen op `gebruikersnaam` zoeken in de nationale database.  
2.  **Koppelen:** Als de gebruiker bestaat, maakt de planner een nieuw `Lidmaatschap` record aan voor zijn eigen team. De gebruiker erft direct de locatie-context.  
3.  **Aanmaken:** Bestaat de gebruikersnaam nog niet? Dan mag de planner een nieuw basis-gebruikersprofiel aanmaken, dat automatisch wordt gekoppeld aan zijn team.  
4.  **Validatie:** De backend blokkeert elke poging van een planner om lidmaatschappen te wijzigen voor teams waar hij zelf geen `is_planner=True` status heeft.

---

## 5. Functionele Scheiding van Schrijfrechten

* **Planning-Objecten:** Mutaties (shift wijzigen/toevoegen) zijn strikt voorbehouden aan de Planner (team-niveau) of Beheerder (locatie-breed).  
* **Self-Service Objecten:** Een Werknemer heeft altijd schrijfrechten op eigen entiteiten:  
    * Verlofaanvragen indienen (status wordt 'In afwachting').  
    * Beschikbaarheid doorgeven.  
    * Notities versturen naar de planner van het eigen team.  
* **HR-Objecten:** HR kan doorgaans geen operationele planning wijzigen, maar wel specifieke HR-velden (bijv. contract-uren of looncodes) aanpassen indien geautoriseerd.

---

## 6. UI Impact: De Locatie-switcher

Gebruikers die lid zijn van teams op verschillende locaties (bijv. Antwerpen en Hasselt) krijgen in de mobiele app en op het dashboard een **Locatie-switcher**.  
* Bij selectie van een locatie worden alle API-calls gefilterd op de `locatie_id` van die context.  
* De 'Rode Lijn' (CAO-check) draait echter altijd op de **totale set** van de gebruiker (alle locaties gecombineerd) om conflicten te voorkomen.

---

## 7. Multi-Role Context (De Beheerder-Planner)

Indien een gebruiker zowel een Locatie-rol (Beheerder) als een Team-rol (Planner) heeft, wordt de interface gescheiden op basis van 'Perspectief':

- **Operationeel Perspectief (Planner):** De API-calls worden gefilterd op `team_id` waar de gebruiker `is_planner=True` heeft. Dit zorgt voor een schone werktafel zonder ruis van andere teams.  
- **Beheer Perspectief (Beheerder):** De API-calls gebruiken de `locatie_id` scope. De gebruiker krijgt toegang tot alle medewerkers en teams binnen de locatie voor administratieve taken.  
- **Gecombineerde Validatie:** De business-logica (Rode Lijn) valideert altijd over de volledige scope van de locatie om overlappingen tussen teams te voorkomen.