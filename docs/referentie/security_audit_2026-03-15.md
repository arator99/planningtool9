# Security Audit Rapport — Planning Tool v0.8

**Datum:** 2026-03-15
**Scope:** FastAPI webapplicatie, backend codebase
**Standaard:** OWASP API Security Top 10

---

## Samenvatting bevindingen

| Ernst | Aantal |
|-------|--------|
| CRITICAL | 3 |
| HIGH | 6 |
| MEDIUM | 5 |
| LOW | 4 |
| INFO | 3 |

---

## Prioriteringsmatrix

| # | Bevinding | Ernst | Inspanning | Prioriteit |
|---|-----------|-------|------------|------------|
| 13 | Geen CSRF-beveiliging | CRITICAL | Hoog | 1 |
| 15 | Zwakke/gedeelde secrets in productie | CRITICAL | Laag | 2 |
| 14 | Forcible logout via CSRF | CRITICAL | Laag | 3 |
| 02 | Geen brute-force bescherming login | HIGH | Laag | 4 |
| 19 | `--reload` in productie Dockerfile | HIGH | Laag | 5 |
| 01 | `secure=False` op sessiecookies | HIGH | Laag | 6 |
| 06 | Ontbrekende gebruiker-groep validatie verlof | HIGH | Laag | 7 |
| 10 | Ongevalideerde pad-parameters planning | HIGH | Laag | 8 |
| 24 | Ontbrekende security headers | MEDIUM | Laag | 9 |
| 08 | Gebruikersstatus-oracle via foutmelding | MEDIUM | Laag | 10 |

---

## 1. Authenticatie en Sessie

### CRITICAL-01 — `secure=False` op alle sessiecookies
**Bestand:** `api/routers/auth.py`

Elke `set_cookie()` gebruikt expliciet `secure=False`. Op de productieomgeving (`https://planningtool.org`) dwingt dit de browser niet om cookies uitsluitend over HTTPS te sturen. Bij directe LAN-toegang (`http://192.168.0.6:8000`) worden sessiecookies in plaintext verstuurd.

**Aanbeveling:** Stel `secure` conditioneel in via `config.instellingen.omgeving`. In productie (`omgeving != "development"`) moet `secure=True`.

---

### HIGH-02 — Geen brute-force bescherming op login
**Bestand:** `api/routers/auth.py`, `requirements.txt`

`slowapi` staat in `requirements.txt` maar is nergens geregistreerd of toegepast. Het loginendpoint `/auth/inloggen` en TOTP-endpoint `/auth/totp/verifieer` hebben geen rate limiting. Een 6-cijferige TOTP-code heeft slechts 1.000.000 combinaties.

**Aanbeveling:** Registreer `slowapi` als middleware in `main.py` en voeg `@limiter.limit("5/minute")` toe aan beide endpoints.

---

### HIGH-03 — Access- en temp-token delen dezelfde geheime sleutel
**Bestand:** `services/domein/auth_domein.py`

Beide token-typen worden gesigneerd met dezelfde `GEHEIME_SLEUTEL` en HS256. De scheiding bestaat alleen via de `stap`-claim. Als die controle door een bug wegvalt, kan een gedeeltelijk geauthenticeerde gebruiker (stap 1) een volledig sessietoken hergebruiken.

**Aanbeveling:** Gebruik een aparte `TOTP_GEHEIME_SLEUTEL`, of voeg een `aud`-claim (audience) toe die strikt gevalideerd wordt bij decodering.

---

### MEDIUM-04 — Geen server-side token invalidatie
**Bestand:** `services/domein/auth_domein.py`

Het sessiecookie heeft geen `max_age` en is dus een sessiecookie. Er is geen server-side invalidatie: als een gebruiker gedeactiveerd wordt of zijn wachtwoord wijzigt, blijft een actief JWT geldig tot de `exp`-claim.

**Aanbeveling:** Voeg een `token_versie` of `jti` (JWT ID) toe aan het gebruikersmodel en valideer dit bij elke tokenverificatie.

---

### MEDIUM-05 — `SameSite=Lax` in plaats van `Strict` op sessiecookie
**Bestand:** `api/routers/auth.py`

`Lax` biedt enige CSRF-bescherming maar staat formulier-POST-requests toe die door gebruikersinteractie op een derde-party site worden geïnitieerd.

**Aanbeveling:** Wijzig naar `samesite="strict"` voor het `toegangs_token`. Het `taal`-cookie mag op `lax` blijven.

---

## 2. Autorisatie en Cross-Tenant Isolatie

### HIGH-06 — Ontbrekende `groep_id`-validatie bij verlof namens andere gebruiker
**Bestand:** `api/routers/verlof.py`

In `verwerk_aanvraag()` controleert de logica niet of de opgegeven `gebruiker_id` tot dezelfde `groep_id` behoort als de behandelaar. Een behandelaar uit groep A kan zo een aanvraag koppelen aan een `gebruiker_id` uit groep B.

**Aanbeveling:** Valideer in de router of service dat de opgegeven `gebruiker_id` tot `gebruiker.groep_id` behoort.

---

### HIGH-07 — Directe `db.query()` in de verlof-router
**Bestand:** `api/routers/verlof.py`

Een directe `db.query(Gebruiker)` in de router is een architectuurschending en vergroot het risico dat toekomstige aanpassingen de verplichte `groep_id`-filter vergeten.

**Aanbeveling:** Verplaats de query naar `GebruikerService` of `VerlofService`.

---

### MEDIUM-08 — Foutmelding lekt gebruikersstatus
**Bestand:** `services/auth_service.py`

Bij een gedeactiveerd account wordt een specifieke foutmelding getoond ("Account is gedeactiveerd"). Dit geeft een aanvaller een oracle om te enumereren welke gebruikersnamen bestaan én actief zijn.

**Aanbeveling:** Toon bij een gedeactiveerd account dezelfde generieke foutmelding ("Ongeldige gebruikersnaam of wachtwoord") en log het intern.

---

### LOW-09 — Geen authenticatie vereist op uitloggen
**Bestand:** `api/routers/auth.py`

Het `/auth/uitloggen` endpoint heeft geen authenticatievereiste. Elke anonieme POST verwijdert de cookies, wat een CSRF-geïnduceerde forcible logout mogelijk maakt.

**Aanbeveling:** Voeg een CSRF-token toe aan het uitlogformulier of een minimale `Referer`-check.

---

## 3. Input Validatie

### HIGH-10 — Ongevalideerde parameters in planning-router
**Bestand:** `api/routers/planning.py`

`datum_str` wordt direct doorgegeven aan `date.fromisoformat()` zonder foutafhandeling (leidt tot 500 in plaats van 422). `regel_code` wordt zonder whitelist doorgegeven aan de `ValidatieService`.

**Aanbeveling:** Gebruik Pydantic `Path`/`Query`-validators voor `datum_str`. Valideer `regel_code` tegen het `VALIDATORS`-register in `services/domein/validatie_domein.py`.

---

### LOW-11 — Foutmeldingen in query parameters
**Bestanden:** `api/routers/gebruikers.py`, `api/routers/verlof.py`

Foutmeldingen uit `ValueError`-exceptions worden direct als query parameter in redirect-URLs gezet. Als input een foutmelding beïnvloedt, kan dit leiden tot URL-injection.

**Aanbeveling:** Gebruik een vaste foutcode of flash-message mechanisme in plaats van vrije tekst in de URL.

---

## 4. CSRF

### CRITICAL-13 — Geen CSRF-beveiliging op state-muterende endpoints
**Bestanden:** Alle `api/routers/*.py` met `@router.post()`

De applicatie heeft geen CSRF-tokenvalidatie. Alle POST-formulieren zijn kwetsbaar. Concrete aanvalsscenario's:
- Verborgen formulier dat POST naar `/beheer/gebruikers/{id}/deactiveer`
- POST naar `/account/wachtwoord` met een door aanvaller gekozen wachtwoord

**Aanbeveling:** Implementeer synchronizer token pattern via `itsdangerous` voor signed CSRF-tokens, of gebruik de `starlette-csrf` middleware.

---

### CRITICAL-14 — Forcible logout via CSRF
**Bestand:** `api/routers/auth.py`

Gecombineerd met LOW-09: het uitlogendpoint heeft geen authenticatie én geen CSRF-token. Een kwaadaardige pagina kan elke ingelogde gebruiker uitloggen.

---

## 5. Gevoelige Data

### CRITICAL-15 — Zwakke/gedeelde secrets in productie
**Bestand:** `v08/.env`

De `GEHEIME_SLEUTEL` heeft een herkenbare development-waarde. Als dezelfde `.env` op de NAS staat, kan een aanvaller die de sleutel kent geldig JWT-tokens aanmaken voor elke `gebruiker_id` en `rol`.

**Aanbeveling:** Genereer op de NAS een unieke sleutel:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Voeg een opstartcontrole toe in `main.py` die weigert te starten als `OMGEVING != "development"` en de sleutel de bekende development-waarde heeft.

---

### MEDIUM-16 — Standaard wachtwoord zichtbaar in applicatielog
**Bestand:** `main.py`

Bij een lege database logt de applicatie het standaard admin-wachtwoord in plaintext naar stdout.

**Aanbeveling:** Verwijder het wachtwoord uit de logoutput.

---

### INFO-17 — TOTP-geheim zichtbaar in HTML-bron
**Bestand:** `api/routers/auth.py`, `templates/pages/totp_instellen.html`

Het TOTP-geheim verschijnt als plaintext in de HTML van de instelpagina.

**Aanbeveling:** Voeg `Cache-Control: no-store` toe aan de response voor `/totp/instellen`.

---

## 6. i18n Module

### LOW-18 — Geen validatie in `_laad()` zelf
**Bestand:** `i18n/__init__.py`

`vertaal()` valideert de taalcode tegen een whitelist, maar `_laad()` (de gecachte laadfunctie) heeft geen eigen validatie. Als `_laad()` direct aangeroepen zou worden met niet-gevalideerde input, is path traversal theoretisch mogelijk.

**Aanbeveling:** Voeg een `assert taal in TALEN` toe in `_laad()` als defence-in-depth.

---

## 7. Docker en Deployment

### HIGH-19 — `--reload` in productie Dockerfile
**Bestand:** `backend/Dockerfile`

`uvicorn` start met `--reload`. In combinatie met de volume mount `./backend:/app` worden code-wijzigingen op de NAS onmiddellijk actief zonder deployment-procedure.

**Aanbeveling:** Gebruik conditioneel opstartcommando op basis van `OMGEVING`. In productie: uvicorn zonder `--reload`, met `--workers 2`.

---

### MEDIUM-20 — Live volume mount in productie
**Bestand:** `docker-compose.yml`

`./backend:/app` mount de volledige broncode als live volume in de container.

**Aanbeveling:** Gebruik een `docker-compose.override.yml` voor development-specifieke mounts. Bouw een nieuw image bij productie-deployment.

---

### LOW-21 — Geen expliciete Docker-netwerken
**Bestand:** `docker-compose.yml`

Containers communiceren via het standaard Docker-netwerk zonder expliciete isolatie.

**Aanbeveling:** Voeg een `networks`-sectie toe voor geïsoleerde interne communicatie.

---

## 8. Dependencies

### INFO-22 — Dependencies niet vastgepind op patch-niveau
**Bestand:** `requirements.txt`

`sqlalchemy>=2.0,<3.0` en `pydantic>=2.0,<3.0` zijn niet vastgepind. Bij herbouw van het Docker image wordt de nieuwste patch-versie geïnstalleerd.

**Aanbeveling:** Genereer een `requirements.lock` via `pip freeze` voor reproduceerbare builds.

---

### LOW-23 — `passlib[bcrypt]` is EOL
**Bestand:** `requirements.txt`

`passlib` heeft geen onderhoud meer ontvangen sinds 2023. De combinatie met `bcrypt==4.0.1` werkt maar is fragiel door breaking changes in bcrypt 4.x.

**Aanbeveling:** Overweeg migratie naar directe `bcrypt`-integratie of `argon2-cffi`.

---

## 9. Ontbrekende Security Headers

### MEDIUM-24 — Geen security response headers
**Bestand:** `main.py`

Ontbrekende headers:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy`

**Aanbeveling:** Voeg een middleware toe in `main.py` die deze headers op alle responses plaatst.

---

## 10. Bevindingen die al correct zijn

### INFO-12 — SQLAlchemy ORM beschermt tegen SQL injection
De volledige datalaag gebruikt geparametreerde queries. Geen raw SQL-strings aangetroffen.
