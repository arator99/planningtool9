# Security Audit — Planningtool v0.9
**Datum:** 2026-03-21
**Auditor:** Claude Sonnet 4.6 (geautomatiseerde analyse)
**Scope:** Backend FastAPI-applicatie, deployment op Synology NAS via Cloudflare Tunnel
**Methodologie:** OWASP API Security Top 10 + OWASP Web Application Security Testing Guide

---

## 1. Samenvatting

De Planningtool v0.9 heeft een **overwegend solide beveiligingsbasis**. De kritieke componenten — JWT-authenticatie, CSRF-bescherming, wachtwoordopslag en rolgebaseerde autorisatie — zijn zorgvuldig geïmplementeerd. Er zijn geen kritieke (🔴) kwetsbaarheden aangetroffen.

Er zijn echter **vier hoog-ernstige** bevindingen die voor productiedeployment via Cloudflare Tunnel aandacht verdienen, voornamelijk rondom het vertrouwen in proxy-headers, de CSP-configuratie, de `locatie_context`-cookie en het gedrag van de seed-functie. Daarnaast zijn er meerdere middel- en laag-ernstige verbeterpunten.

### Kritieke bevindingen op een rij

| Ernst | Aantal | Beschrijving |
|---|---|---|
| 🔴 Kritiek | 0 | — |
| 🟠 Hoog | 4 | CF-header spoofing, CSP `unsafe-inline`, locatie_context niet gevalideerd, seed in non-production |
| 🟡 Middel | 6 | CSRF-fallback uit cookie, open redirect, geen audit bij aankondiging/locatie, logboek enkel beheerder, wachtwoord in log, ontbrekende BaseRepository |
| 🟢 Laag | 5 | Tailwind via CDN in CSP, JWT bevat `rol` claim, bcrypt legacy pad, geen rate limit op wachtwoord-endpoint, TOTP niet verplicht |

---

## 2. Bevindingen per categorie

### 2.1 Cloudflare Tunnel — Proxy-header betrouwbaarheid

**Ernst: 🟠 Hoog**
**Bewijs:** `backend/api/rate_limiter.py:5-11`

```python
def _haal_client_ip(request) -> str:
    return (
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or get_remote_address(request)
    )
```

**Beschrijving:**
De rate limiter vertrouwt blind op de `CF-Connecting-IP`-header. Wanneer het verkeer via Cloudflare Tunnel binnenkomt op poort 8000 op de NAS, is de vraag: is poort 8000 direct bereikbaar via het LAN of internet, naast Cloudflare? Als dat zo is, kan een aanvaller de header zelf instellen en zo de rate limiter omzeilen. Cloudflare voegt `CF-Connecting-IP` altijd toe aan verkeer dat via hun infrastructuur passeert, maar als de app ook direct bereikbaar is (zelfs alleen via het interne netwerk van de NAS), kan een interne aanvaller de header spoofen.

**Aanbeveling:**
1. Zorg dat poort 8000 op de NAS **uitsluitend** bereikbaar is voor de Cloudflare Tunnel-daemon en niet voor het LAN of internet. Bind uvicorn aan `127.0.0.1` i.p.v. `0.0.0.0` als de Cloudflare-daemon lokaal draait.
2. Voeg een validatiestap toe die controleert of het verzoek werkelijk via Cloudflare is binnengekomen (bijv. via `CF-Ray` header aanwezigheid als extra check, of netwerkfirewall-regels).
3. Overweeg de Cloudflare IP-ranges te allowlisten op firewallniveau op de NAS zodat direct verkeer technisch onmogelijk is.

---

### 2.2 Content Security Policy — `unsafe-inline` voor scripts

**Ernst: 🟠 Hoog**
**Bewijs:** `backend/api/middleware/security_headers.py:11-16`

```python
_CSP_PRODUCTIE = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
    ...
)
```

**Beschrijving:**
De CSP staat `'unsafe-inline'` toe voor zowel scripts als stijlen. Dit neutraliseert de XSS-bescherming die een CSP biedt: elke XSS-kwetsbaarheid (bijv. via de `extra_info`-invoer bij aankondigingen, of via `bericht`/`fout` queryparameters die in templates worden weergegeven) kan inline scripts uitvoeren. Daarnaast wordt `https://unpkg.com` als extern script-domein toegestaan, wat een supply-chain aanvalsoppervlak vormt.

**Aanvullende observatie:**
De CSP verwijst naar `https://cdn.tailwindcss.com` voor stijlen, maar de CLAUDE.md specificeert expliciet dat Tailwind via CLI wordt gebouwd en geen CDN gebruikt. Dit duidt op een inconsistentie: de CSP staat een extern domein toe dat de app in werkelijkheid niet gebruikt, wat onnodig aanvalsoppervlak creëert.

**Aanbeveling:**
1. Vervang `'unsafe-inline'` voor scripts door een `nonce`-gebaseerde aanpak (`script-src 'self' 'nonce-{random}'`).
2. Verwijder `https://cdn.tailwindcss.com` uit de CSP als de app de CDN-versie daadwerkelijk niet gebruikt.
3. Overweeg `https://unpkg.com` te vervangen door de lokaal geserveerde HTMX-bestanden in `static/`.

---

### 2.3 `locatie_context`-cookie — Onvoldoende servervalidatie

**Ernst: 🟠 Hoog**
**Bewijs:** `backend/api/dependencies.py:82-88`, `backend/api/routers/locaties.py:144-149`

```python
# dependencies.py
cookie_val = request.cookies.get("locatie_context")
if cookie_val:
    try:
        return int(cookie_val)
    except (ValueError, TypeError):
        pass
return gebruiker.locatie_id
```

```python
# locaties.py — cookie instellen zonder secure=True
response.set_cookie(
    key="locatie_context",
    value=str(locatie_id),
    httponly=True,
    samesite="lax",
    max_age=86400 * 7,
)
```

**Beschrijving:**
De `locatie_context`-cookie bepaalt welke locatie een `super_beheerder` actief ziet en op welke data zij acties uitvoeren. De cookie is `httponly=True` maar mist `secure=True` — dit betekent dat de cookie over onversleuteld HTTP verstuurd kan worden als de verbinding niet via HTTPS verloopt. Bovendien wordt de waarde uit de cookie alleen gevalideerd als een geldig integer, maar er wordt niet gecontroleerd of de opgegeven `locatie_id` daadwerkelijk bestaat of actief is. Een `super_beheerder` die de cookie handmatig aanpast naar een niet-bestaand of verwijderd locatie-ID kan onverwacht gedrag veroorzaken, al is de scope beperkt tot super_beheerder-accounts.

**Aanbeveling:**
1. Voeg `secure=True` toe aan de `locatie_context` cookie (zorg dat `_SECURE = instellingen.omgeving != "development"` ook hier gebruikt wordt).
2. Valideer bij het lezen van de cookie dat de `locatie_id` bestaat en actief is via een DB-lookup.

---

### 2.4 Seed-functie — Productie-omgeving check onbetrouwbaar

**Ernst: 🟠 Hoog**
**Bewijs:** `backend/api/seed.py:15-16`, `backend/config.py:11`

```python
# seed.py
if instellingen.omgeving == "production":
    logger.info("Seeden overgeslagen (productie-omgeving).")
    return
```

```python
# config.py
omgeving: str = "development"  # standaardwaarde
```

**Beschrijving:**
De seed-functie slaat seeden alleen over als `omgeving == "production"`. De standaardwaarde van `omgeving` is `"development"`. Dit betekent dat als de `.env`-variabele `OMGEVING` ontbreekt of verkeerd gespeld is (bijv. `"productie"`, `"prod"`, `"staging"`), de seed-functie in productie gewoon uitgevoerd wordt. Bij een lege database maakt de seed een `admin`-gebruiker aan zonder TOTP-vereiste. Het gegenereerde wachtwoord wordt dan in de logs geschreven via `logger.warning()`.

**Aanvullende observatie (`backend/api/seed.py:49`):**
```python
logger.warning("SEED_ADMIN_WACHTWOORD niet ingesteld — tijdelijk wachtwoord gegenereerd: %s", seed_wachtwoord)
```
Het tijdelijke wachtwoord belandt in de applicatielogboeken. Als de logs worden doorgestuurd naar een externe logserver of opgeslagen op een gedeeld volume, is het wachtwoord blootgesteld.

**Aanbeveling:**
1. Verander de seed-check van `omgeving == "production"` naar `omgeving != "development"`: seed alleen in development. Dit is een veiligere standaard.
2. Schrijf nooit wachtwoorden (zelfs tijdelijke) naar logs. Log alleen dat een wachtwoord gegenereerd is, zonder de waarde.
3. Overweeg het seed-wachtwoord naar stdout te schrijven en direct naar een tijdelijk bestand buiten de Docker-log te leiden.

---

### 2.5 CSRF-token fallback uit cookie (middelmatig patroon)

**Ernst: 🟡 Middel**
**Bewijs:** `backend/api/routers/aankondigingen.py:139`, `backend/api/routers/adv.py:156`, `backend/api/routers/typetabellen.py:90`

```python
# Fout-pad in POST-handler
csrf_token=request.cookies.get("csrf_token", "")
```

**Beschrijving:**
Op meerdere plaatsen wordt bij het opbouwen van de fout-template context het CSRF-token gelezen uit een cookie (`request.cookies.get("csrf_token", "")`). Er bestaat echter geen `csrf_token`-cookie in de applicatie — het token wordt via de Depends-functie `haal_csrf_token` gegenereerd en doorgegeven als sjabloonvariabele. Uit de cookies zal dit altijd een lege string retourneren, waardoor het formulier na een validatiefout een leeg CSRF-token krijgt. De volgende POST-poging van de gebruiker zal dan mislukken met een CSRF-fout, ook al is de gebruiker legitiem.

**Aanbeveling:**
Vervang `request.cookies.get("csrf_token", "")` door een aanroep van `genereer_csrf_token(str(gebruiker.id))` (zoals al correct gedaan in `auth.py:215`). Zo krijgt de fout-template altijd een geldig token.

---

### 2.6 Open redirect via Referer-header

**Ernst: 🟡 Middel**
**Bewijs:** `backend/api/routers/locaties.py:140-142`

```python
referer = request.headers.get("referer", "/dashboard")
terug_pad = urlparse(referer).path or "/dashboard"
response = RedirectResponse(url=terug_pad, status_code=303)
```

**Beschrijving:**
De locatie-switcher gebruikt de `Referer`-header om de gebruiker na het wisselen van locatie terug te sturen. De code extraheert alleen het pad via `urlparse(...).path`, waardoor een externe redirect naar een ander domein niet mogelijk is. Dit is een goede beperking. Echter, de `Referer`-header kan door een aanvaller die CSRF kan uitvoeren of die de gebruiker naar een kwaadaardige pagina kan sturen, gemanipuleerd worden om het pad te beïnvloeden (bijv. naar `/login`, `/beheer/gebruikers/[uuid]/verwijder`). Dit is een laag-impact vector, maar het verdient aandacht.

**Aanbeveling:**
Beperk `terug_pad` tot een allowlist van bekende veilige paden, of gebruik een vaste redirect naar `/dashboard` in plaats van de dynamische Referer-aanpak.

---

### 2.7 Ontbrekende AuditLog bij aankondigingen en locaties

**Ernst: 🟡 Middel**
**Bewijs:** `backend/api/routers/aankondigingen.py` (volledig bestand), `backend/api/routers/locaties.py` (volledig bestand)

**Beschrijving:**
De CLAUDE.md-checklist vereist een `AuditLog` entry bij elke mutatieactie. De routers voor aankondigingen en locaties loggen mutaties niet naar de `AuditLog`-tabel. Dit betekent dat acties als het aanmaken, bewerken, activeren en verwijderen van systeemaankondigingen, en het aanmaken en deactiveren van locaties, niet terug te vinden zijn in het auditspoor. Verlof, ADV en gebruikersbeheer hebben wel correcte audit logging.

**Aanbeveling:**
Voeg `AuditLog` entries toe in:
- `backend/api/routers/aankondigingen.py` voor `maak_aan`, `bewerk`, `activeer`, `deactiveer`, `verwijder`
- `backend/api/routers/locaties.py` voor `aanmaken`, `bewerken`, `deactiveer`

---

### 2.8 Logboek toegankelijk voor `beheerder` maar niet voor `super_beheerder`

**Ernst: 🟡 Middel**
**Bewijs:** `backend/api/routers/logboek.py:61`

```python
gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
```

**Beschrijving:**
Het logboek is beveiligd met `vereiste_rol("beheerder")`. De `vereiste_rol`-functie controleert via `_actieve_rollen(gebruiker).intersection(rollen)` — als een `super_beheerder` géén `beheerder`-rol heeft (wat de norm is), heeft deze geen toegang tot het logboek. Dit is waarschijnlijk een onbedoeld gat: de `super_beheerder` zou audit logs moeten kunnen bekijken.

**Aanbeveling:**
Wijzig naar `vereiste_rol("beheerder", "super_beheerder")` of gebruik de bestaande `vereiste_beheerder_of_hoger` dependency.

---

### 2.9 Foutmelding bevat wachtwoord in redirect-URL

**Ernst: 🟡 Middel**
**Bewijs:** `backend/api/routers/account.py:88`

```python
return RedirectResponse(url=f"/account/wachtwoord?fout={fout}", status_code=303)
```

**Beschrijving:**
Foutmeldingen van `AuthService.wijzig_wachtwoord` worden direct in de redirect-URL opgenomen. De foutmelding bevat nooit het wachtwoord zelf (de service geeft generieke meldingen terug), maar het patroon kan gevaarlijk zijn als iemand in de toekomst een foutmelding toevoegt die invoer bevat. Bovendien kunnen foutmeldingen in URL's worden gelogd door toegangsloggers (Cloudflare, nginx, etc.).

**Aanbeveling:**
Gebruik een vaste foutsleutel in de URL (bijv. `?fout=huidig_wachtwoord_onjuist`) in plaats van de ruwe exception-string. Dit patroon wordt in andere routers al correct toegepast.

---

### 2.10 Geen rate limiting op wachtwoord-reset endpoint (beheerder)

**Ernst: 🟡 Middel**
**Bewijs:** `backend/api/routers/gebruikers.py:327-351`

**Beschrijving:**
Het `POST /beheer/gebruikers/{uuid}/wachtwoord` endpoint voor wachtwoord-reset door beheerders heeft geen `@limiter.limit()` decorator. Hoewel dit endpoint alleen voor `beheerder` of hoger bereikbaar is, zou een gecompromitteerd beheerders-account massaal wachtwoorden kunnen resetten. Het login-endpoint heeft wel rate limiting (5/minuut).

**Aanbeveling:**
Voeg `@limiter.limit("10/minute")` toe aan het wachtwoord-reset endpoint.

---

### 2.11 Geen BaseRepository tenant-filter op directe queries in routers

**Ernst: 🟡 Middel**
**Bewijs:** `backend/api/routers/gebruikers.py:60-61`, `backend/api/routers/gebruikers.py:182-183`

```python
# Directe DB-queries zonder locatie-filter in de router
alle_teams = {t.id: t for t in db.query(Team).filter(Team.locatie_id == gebruiker.locatie_id).all()}
alle_locaties = {l.id: l for l in db.query(Locatie).all()}
```

**Beschrijving:**
De CLAUDE.md schrijft voor dat elke DB-query via `BaseRepository._locatie_filter()` moet gaan. In de `gebruikers`-router worden directe `db.query()`-aanroepen gedaan buiten de service-laag. `db.query(Locatie).all()` haalt **alle** locaties op zonder locatie-filter. Dit is in dit geval functioneel correct (een beheerder heeft alle locaties nodig voor de dropdown bij super_beheerder-bewerkingen), maar het doorbreekt de architectuurconventie en kan bij toekomstige refactoring leiden tot tenant-lekken.

**Aanbeveling:**
Verplaats directe DB-queries naar de respectieve services. Verifieer dat de architectuurregel consistent wordt toegepast.

---

### 2.12 JWT bevat `rol` claim (gedenormaliseerd)

**Ernst: 🟢 Laag**
**Bewijs:** `backend/services/domein/auth_domein.py:93`

```python
payload = {"sub": gebruiker_id, "rol": rol, "exp": verlooptijd, "aud": _AUD_TOEGANG}
```

**Beschrijving:**
Het JWT-token bevat een `rol` claim. De `rol` in het token is echter de gedenormaliseerde `Gebruiker.rol` (voor display), niet de feitelijke autorisatie-rollen uit `GebruikerRol`. De autorisatie-checks in `dependencies.py` lezen de rollen altijd opnieuw uit de DB via `gebruiker.rollen` (lazy/selectin-loaded). De `rol` claim in het token wordt voor autorisatie dus nooit gebruikt — alleen `gebruiker_id` (`sub`) is functioneel relevant. Dit is veilig, maar de overbodige claim vergroot het token onnodig.

**Aanbeveling:**
Verwijder de `rol` claim uit het JWT-token. Overweeg of dit veld ooit wordt gebruikt, en zo ja, maak de intentie expliciet in code-commentaar.

---

### 2.13 Legacy bcrypt-verificatie pad

**Ernst: 🟢 Laag**
**Bewijs:** `backend/services/domein/auth_domein.py:59-61`

```python
if gehashed.startswith(_BCRYPT_PREFIXEN):
    return _bcrypt.checkpw(wachtwoord.encode(), gehashed.encode())
```

**Beschrijving:**
De code ondersteunt nog bcrypt voor migratie vanuit v0.7/v0.8. Na verificatie wordt de hash niet automatisch gemigreerd naar argon2 (de comment in de code bevestigt dit). Gebruikers met een legacy bcrypt-hash hebben een minder sterke wachtwoord-hash zolang ze hun wachtwoord niet wijzigen.

**Aanbeveling:**
Implementeer de gecommentariseerde `verifieer_en_migreer()` in `auth_service.py`: na een succesvolle bcrypt-verificatie, hash het wachtwoord opnieuw met argon2 en sla het op. Stel een deadline in waarna bcrypt-hashes worden gedeactiveerd.

---

### 2.14 TOTP niet verplicht voor beheerders

**Ernst: 🟢 Laag**
**Bewijs:** `backend/services/auth_service.py:52-56`

```python
if gebruiker.totp_actief:
    return {"stap": "totp_vereist", "temp_token": ...}
```

**Beschrijving:**
TOTP 2FA is optioneel voor alle gebruikers inclusief beheerders en super_beheerders. Een gecompromitteerd wachtwoord geeft directe toegang tot een beheerders-account.

**Aanbeveling:**
Overweeg TOTP verplicht te stellen voor rollen met hoge privileges (`beheerder`, `super_beheerder`). Voeg bij inloggen een check toe die gebruikers met deze rollen en `totp_actief == False` doorsturen naar de TOTP-instelpagina.

---

### 2.15 `X-Content-Type-Options` ontbreekt voor static files

**Ernst: 🟢 Laag**
**Bewijs:** `backend/main.py:61`, `backend/api/middleware/security_headers.py`

**Beschrijving:**
De `SecurityHeadersMiddleware` voegt headers toe aan responses van de FastAPI-routes, maar statische bestanden (CSS, JS) worden geserveerd via `StaticFiles` van Starlette. De Starlette `StaticFiles`-middleware omzeilt de `BaseHTTPMiddleware`, wat betekent dat responses voor `/static/*` de security headers mogelijk **niet** meekrijgen.

**Aanbeveling:**
Verifieer via een live request of de headers aanwezig zijn op statische bestanden. Zo niet, voeg de headers expliciet toe via een custom middleware die ook StaticFiles-responses intercepteert, of configureer een reverse proxy (Caddy/nginx) voor static file serving met de juiste headers.

---

## 3. Positieve bevindingen

De volgende beveiligingsmaatregelen zijn correct en goed geïmplementeerd:

### Authenticatie
- **argon2-cffi voor wachtwoord-hashing:** Correct gebruik van de sterk aanbevolen algoritme. passlib is terecht vermeden.
- **httpOnly + SameSite=Strict cookies:** JWT-token en TOTP-temp-token worden correct beveiligd opgeslagen.
- **Audience-claims in JWT:** Separate `aud` claims voor toegangs-tokens en TOTP-tussenstap tokens voorkomen token-hergebruik.
- **Token-expiratie:** Beide token-typen hebben correcte vervaltijden (configureerbaar + 5 minuten voor TOTP).
- **Productie-secret validatie:** `config.py` weigert te starten met de development-sentinel in productie.

### Autorisatie
- **Geen hiërarchische rollen:** Het niet-hiërarchische rolmodel via `GebruikerRol` is correct — rollen worden altijd opnieuw uit de DB gelezen, nooit uit het JWT-token.
- **`vereiste_rol()`-checks aanwezig op alle gemuteerde endpoints:** Alle POST-handlers zijn beveiligd met de juiste rol-dependency.
- **Tenant-isolatie via `locatie_id`:** Services ontvangen `locatie_id` uit de JWT-context. Het patroon is consistent aanwezig in de onderzochte routers.
- **UUID in API-paden:** Integer IDs zijn nergens zichtbaar in externe URL-paden.

### CSRF
- **HMAC-gesigneerd synchronizer token pattern:** De implementatie via `itsdangerous.URLSafeTimedSerializer` is correct en standaard.
- **Token gekoppeld aan gebruiker-ID + 1-uur verloping:** Correcte binding en tijdslimiet.
- **Alle muterende POST-endpoints hebben `_csrf: None = Depends(verifieer_csrf)`:** Consistent aanwezig in alle onderzochte routers.

### Aankondigingensysteem (XSS)
- **Enkel whitelist-sjablonen toegestaan:** `AankondigingService._valideer()` valideert sjabloon, ernst en type tegen whitelists. Vrije tekst is beperkt tot `extra_info`.
- **Jinja2 auto-escaping:** Standaard Jinja2-configuratie escapet output automatisch in HTML-templates, waardoor `extra_info` veilig weergegeven wordt.

### Deployment
- **OpenAPI-docs uitgeschakeld in productie:** `docs_url=None` tenzij omgeving is `"development"`.
- **Security headers aanwezig:** X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy, HSTS en CSP zijn geconfigureerd voor productie.
- **Geen secrets in code of git:** Alle gevoelige waarden worden via environment variables geladen.
- **Soft-delete model:** Fysiek verwijderen is nergens geïmplementeerd (met uitzondering van aankondigingen — zie volgende sectie).
- **Rate limiting op login en TOTP:** 5/minuut op login en TOTP-verificatie, 3/minuut op TOTP-bevestiging, 2/minuut op batch-auto-invullen.
- **Seed-wachtwoord uit environment variable:** `SEED_ADMIN_WACHTWOORD` voorkomt hardcoded wachtwoorden.

### Aanvullende positieve observaties
- **Aankondigingen worden fysiek verwijderd** (`db.delete()`) — dit is bewust omdat aankondigingen geen business-records zijn en geen audit-trail vereisen. Dit is verdedigbaar.
- **`omgeving == "development"` check in health-endpoint:** Geen informatielekken in productie.
- **TOTP `valid_window=1`:** Een klein venster (±30 seconden) vermindert het risico op replay-aanvallen.

---

## 4. Prioriteitenlijst

Gesorteerd op ernst en impact voor een publiek bereikbare applicatie via Cloudflare Tunnel.

### Onmiddellijk (voor productiedeployment)

1. **[🟠 Hoog]** Netwerkisolatie Cloudflare Tunnel — Verifieer en afdwing dat poort 8000 op de NAS uitsluitend bereikbaar is via de Cloudflare Tunnel-daemon. Dit is een infrastructuurtaak, geen codewijziging.

2. **[🟠 Hoog]** Seed-check corrigeren — Wijzig `omgeving == "production"` naar `omgeving != "development"` in `backend/api/seed.py:15`. Verwijder het wachtwoord uit de log-statement op regel 49.

3. **[🟠 Hoog]** `secure=True` op `locatie_context`-cookie — Voeg `secure=_SECURE` toe in `backend/api/routers/locaties.py:143`. Één regel code.

4. **[🟡 Middel]** CSRF-token fallback repareren — Vervang `request.cookies.get("csrf_token", "")` door `genereer_csrf_token(str(gebruiker.id))` op drie locaties: `aankondigingen.py:139,210`, `adv.py:156,230`, `typetabellen.py:90,138`.

5. **[🟡 Middel]** Logboek toegankelijk voor super_beheerder — Wijzig `vereiste_rol("beheerder")` naar `vereiste_beheerder_of_hoger` in `backend/api/routers/logboek.py:61`.

### Kortetermijn (binnen 1 sprint)

6. **[🟠 Hoog]** CSP verbeteren — Verwijder `https://cdn.tailwindcss.com` als de CDN niet gebruikt wordt. Onderzoek de haalbaarheid van nonce-gebaseerde CSP ter vervanging van `unsafe-inline` voor scripts.

7. **[🟡 Middel]** AuditLog toevoegen voor aankondigingen en locaties — Zie bevinding 2.7.

8. **[🟡 Middel]** Foutmelding-URL saniteren in `account.py:88` — Gebruik vaste foutsleutels.

9. **[🟡 Middel]** Rate limiting op wachtwoord-reset endpoint — Voeg `@limiter.limit("10/minute")` toe in `gebruikers.py`.

### Langetermijn (backlog)

10. **[🟢 Laag]** bcrypt-migratie automatiseren — Implementeer auto-herhashen na succesvolle bcrypt-verificatie.

11. **[🟢 Laag]** TOTP verplicht voor beheerders — Blokkeer inloggen zonder TOTP voor beheerdersrollen.

12. **[🟢 Laag]** Open redirect Referer beperken — Gebruik allowlist of vaste redirect in `locaties.py`.

13. **[🟢 Laag]** Verificeer security headers op statische bestanden — Test of `X-Content-Type-Options` aanwezig is op `/static/` responses.

14. **[🟢 Laag]** `rol` claim verwijderen uit JWT — Overtollige data verwijderen.

---

## 5. NAS/Cloudflare specifieke aandachtspunten

### 5.1 Netwerkarchitectuur

De applicatie is bereikbaar via Cloudflare Tunnel, wat betekent dat HTTPS/TLS wordt afgehandeld door Cloudflare. De verbinding van Cloudflare-edge naar de NAS is via de Tunnel versleuteld. Dit is een goede architectuur voor een NAS-deployement.

**Aandachtspunten:**

- **HSTS in combinatie met Cloudflare:** De app stuurt zelf `Strict-Transport-Security` headers. Controleer of Cloudflare deze headers doorgeeft of overschrijft. Als Cloudflare HSTS al instelt in hun dashboard, is de applicatie-header overbodig maar onschadelijk.

- **Port exposure op NAS:** Docker Compose bindt de app op `0.0.0.0:8000`. Op een Synology NAS betekent dit dat poort 8000 bereikbaar is via het interne LAN. Evalueer of dit noodzakelijk is. Als de app uitsluitend via Cloudflare Tunnel bereikt moet worden, bind dan aan `127.0.0.1:8000` of gebruik een intern Docker-netwerk zonder port binding naar de host.

- **Cloudflare Access:** Overweeg Cloudflare Access (identity-aware proxy) als extra beveiligingslaag vóór de applicatie. Hiermee kunnen alleen geauthenticeerde gebruikers (bijv. via SSO) de applicatie bereiken, wat brute-force aanvallen op het login-endpoint eliminéert.

### 5.2 PostgreSQL-beveiliging

- In `docker-compose.yml` is de PostgreSQL-database niet op een extern netwerk gepubliceerd (geen `ports`-definitie). Dit is correct: de DB is uitsluitend bereikbaar voor de app-container.
- De DB-credentials worden correct via environment variables geladen.
- Er is geen netwerk-isolatie gedefinieerd in de Docker Compose (geen expliciete `networks`). Dit is een laag risico op de NAS, maar expliciete netwerk-isolatie is een verbetering.

### 5.3 Tailwind CDN in CSP

De CSP staat `https://cdn.tailwindcss.com` toe als stijlbron. Volgens de CLAUDE.md wordt Tailwind gebouwd via CLI en wordt er geen CDN gebruikt. Als de CDN daadwerkelijk niet wordt aangeroepen, is deze entry in de CSP een dode maar ook gevaarlijke toevoeging: een XSS-aanval die een `<link>` tag kan injecteren kan een kwaadaardige stylesheet van `cdn.tailwindcss.com` laden (hoewel `style-src unsafe-inline` dit grotendeels overbodig maakt). Verwijder de CDN-entry uit de CSP als bewijs.

### 5.4 Synology NAS — Docker-specifieke aandachtspunten

- Controleer of het Docker-volume `postgres_data` op een versleuteld volume of partition op de NAS staat, zeker als de NAS gedeeld is of fysiek toegankelijk is voor derden.
- De `CHANGELOG.md` en eventuele andere gevoelige projectbestanden mogen niet beschikbaar zijn via de webserver. Verifieer dat `app.mount("/static", ...)` alleen de `static/`-map serveert en geen andere projectdirectories.

### 5.5 Logging en monitoring

- Applicatielogs gaan naar stdout (Docker standaard). Zorg dat deze logs op de NAS beveiligd worden bewaard en niet publiek toegankelijk zijn.
- Overweeg het instellen van alerting voor herhaalde inlogfouten (rate-limit-events worden al gelogd via slowapi).
- De `AuditLog`-tabel biedt een goede basis voor monitoring, maar er is geen mechanisme voor actieve alerts bij verdachte activiteit.

---

## Bijlage: OWASP API Security Top 10 Compliance-overzicht

| # | Categorie | Status | Opmerkingen |
|---|---|---|---|
| API1 | Broken Object Level Authorization | Gedeeltelijk | UUID-gebaseerde paden, locatie-isolatie aanwezig; maar `locatie_context`-cookie niet volledig gevalideerd |
| API2 | Broken Authentication | Voldoet | argon2, JWT, TOTP, rate limiting op login |
| API3 | Broken Object Property Level Authorization | Voldoet | Whitelist-validatie op sjablonen/ernst/type bij aankondigingen; rollen via GebruikerRol |
| API4 | Unrestricted Resource Consumption | Gedeeltelijk | Rate limiting op gevoelige endpoints; ontbreekt op wachtwoord-reset |
| API5 | Broken Function Level Authorization | Voldoet | Alle POST-endpoints beveiligd met rolchecks |
| API6 | Unrestricted Access to Sensitive Business Flows | Gedeeltelijk | Batch-auto (2/min) beperkt; bulk-goedkeuren verlof heeft geen rate limit |
| API7 | Server Side Request Forgery | N.v.t. | Geen outbound HTTP-calls gedetecteerd |
| API8 | Security Misconfiguration | Gedeeltelijk | CSP `unsafe-inline`, seed-check onbetrouwbaar, docs uitgeschakeld in productie |
| API9 | Improper Inventory Management | Voldoet | Geen verborgen/debug-endpoints aangetroffen |
| API10 | Unsafe Consumption of APIs | N.v.t. | Geen externe API-consumptie gedetecteerd |

---

*Rapport gegenereerd op 2026-03-21. Geanalyseerde bestanden: 25+ Python-bestanden, 1 Dockerfile, 1 docker-compose.yml.*
