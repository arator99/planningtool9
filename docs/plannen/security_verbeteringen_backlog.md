# Plan van aanpak — Security verbeteringen backlog
**Datum:** 2026-03-21
**Referentie:** `docs/rapporten/security_audit_2026-03-21.md` + `docs/rapporten/nas_security_audit_2026-03-21.md`

Vier openstaande beveiligingspunten na de audit van 2026-03-21. De "onmiddellijk"- en kortetermijnfixes zijn reeds toegepast (zie CHANGELOG v0.9.1). Dit document beschrijft de overblijvende items in volgorde van aanpak.

---

## Overzicht openstaande items

| # | Item | Ernst | Type |
|---|---|---|---|
| 1 | AuditLog voor aankondigingen en locaties | 🟡 Middel | Codewijziging |
| 2 | CF-header spoofing — NAS firewall afsluiten | 🟠 Hoog | Infrastructuur |
| 3 | CSP `unsafe-inline` → nonce-gebaseerd | 🟠 Hoog | Grotere refactoring |
| 4 | bcrypt auto-migratie + TOTP verplicht voor beheerders | 🟢 Laag | Bewuste backlog |

---

## Item 1 — AuditLog voor aankondigingen en locaties

**Ernst:** 🟡 Middel
**Geschatte omvang:** Klein (< 30 regels)

### Probleemstelling

De `AuditLog`-tabel wordt niet gevuld bij mutaties op aankondigingen en locaties. Verlof, ADV, gebruikers en typetabellen hebben wél audit logging. Dit doorbreekt het auditspoor voor super_beheerder-acties.

### Betrokken bestanden

- `backend/api/routers/aankondigingen.py` — 5 muterende endpoints
- `backend/api/routers/locaties.py` — 3 muterende endpoints

### Aanpak

Een privé hulpfunctie `_log()` toevoegen aan beide routers (identiek patroon als in `gebruikers.py:25-31`):

```python
def _log(db: Session, gebruiker_id: int, locatie_id: int, actie: str, doel_id: int | None = None) -> None:
    try:
        db.add(AuditLog(gebruiker_id=gebruiker_id, locatie_id=locatie_id, actie=actie,
                        doel_type="Aankondiging", doel_id=doel_id))
        db.commit()
    except Exception as exc:
        logger.warning("Audit log mislukt (%s): %s", actie, exc)
```

**aankondigingen.py** — te loggen acties na elke succesvolle operatie:

| Endpoint | Actie |
|---|---|
| `POST /beheer/aankondigingen/nieuw` (succes) | `aankondiging.aanmaken` |
| `POST /beheer/aankondigingen/{uuid}/bewerk` (succes) | `aankondiging.bewerken` |
| `POST /beheer/aankondigingen/{uuid}/activeer` | `aankondiging.activeren` |
| `POST /beheer/aankondigingen/{uuid}/deactiveer` | `aankondiging.deactiveren` |
| `POST /beheer/aankondigingen/{uuid}/verwijder` | `aankondiging.verwijderen` |

**locaties.py** — te loggen acties:

| Endpoint | Actie |
|---|---|
| `POST /beheer/locaties/nieuw` (succes) | `locatie.aanmaken` |
| `POST /beheer/locaties/{uuid}/bewerk` (succes) | `locatie.bewerken` |
| `POST /beheer/locaties/{uuid}/deactiveer` (succes) | `locatie.deactiveren` |

**Let op voor aankondigingen:** het `doel_id` is pas beschikbaar na `maak_aan()` → de service moet de aangemaakte instantie teruggeven. Check `aankondiging_service.maak_aan()` retourneert al een `Aankondiging`-object.

**Let op voor locaties:** `locatie_id` voor de AuditLog is de NAT-locatie-ID (`gebruiker.locatie_id`) omdat locaties zelf het subject zijn, niet een tenant.

### Checklist

- [ ] `_log()` hulpfunctie toevoegen aan `aankondigingen.py`
- [ ] Imports toevoegen: `from models.audit_log import AuditLog`
- [ ] Logging toevoegen bij 5 aankondigingen-endpoints (na redirect-regel, dus: haal eerst het object op vóór redirect)
- [ ] `_log()` hulpfunctie toevoegen aan `locaties.py`
- [ ] Logging toevoegen bij 3 locaties-endpoints
- [ ] Nieuwe actiecodes toevoegen aan `_BEKENDE_ACTIES` in `logboek.py`
- [ ] Testen: aankondiging aanmaken → controle in `/logboek`

---

## Item 2 — CF-header spoofing: NAS firewall afsluiten

**Ernst:** 🟠 Hoog
**Type:** Infrastructuurtaak op de NAS — geen codewijziging
**Referentie:** NAS audit bevinding 3.2 + app audit bevinding 2.1

### Probleemstelling

Poort 8000 is na de `docker-compose.yml`-fix gebonden aan `127.0.0.1`, dus niet meer rechtstreeks bereikbaar via het LAN. Toch is een extra firewallregel wenselijk als tweede vangnet: mocht de binding ooit per ongeluk terug naar `0.0.0.0` gaan (bijv. bij een config-reset), beschermt de firewall nog steeds.

De rate limiter vertrouwt op `CF-Connecting-IP`. Als de app bereikbaar is zonder Cloudflare, kan een aanvaller deze header zelf instellen.

### Uit te voeren stappen op de NAS (DSM)

1. **Verificatie binding:**
   Na deploy op NAS: `docker exec planningtool-app-1 ss -tlnp | grep 8000`
   Verwacht: `127.0.0.1:8000` — niet `0.0.0.0:8000`

2. **DSM Firewall-regel (optionele extra laag):**
   DSM → Configuratiescherm → Beveiliging → Firewall → Regels bewerken:
   - Poort 8000 blokkeren voor alle bronnen behalve `127.0.0.1`
   - (De Cloudflare Tunnel daemon communiceert via intern Docker-netwerk, niet via host-poort)

3. **Cloudflare Access overwegen:**
   Via Cloudflare-dashboard → Zero Trust → Access → Applications:
   - Identity-aware proxy vóór de applicatie instellen
   - Verhindert brute-force op het login-endpoint volledig

4. **CF-Ray header validatie (optioneel, defensieve code):**
   In `rate_limiter.py` een waarschuwing loggen als `CF-Connecting-IP` aanwezig is maar `CF-Ray` ontbreekt — dit duidt op spoofing.

### Checklist

- [ ] Na NAS-deploy: `127.0.0.1:8000` binding verifiëren
- [ ] DSM-firewallregel instellen voor poort 8000
- [ ] Cloudflare Access evalueren (optioneel, zie Zero Trust dashboard)

---

## Item 3 — CSP `unsafe-inline` → nonce-gebaseerd

**Ernst:** 🟠 Hoog
**Type:** Grotere refactoring — aanpak in fasen
**Referentie:** App audit bevinding 2.2

### Probleemstelling

De huidige CSP staat `'unsafe-inline'` toe voor scripts (`script-src`). Dit maakt inline `<script>`-tags overal geldig, waardoor een XSS-kwetsbaarheid (bijv. via ongefilterde foutberichten in templates of `extra_info`-velden) inline code kan uitvoeren. Met een nonce-gebaseerde CSP wordt elke inline script-tag ongeldig tenzij voorzien van het correcte nonce.

`'unsafe-inline'` voor styles is minder kritiek (CSS-injectie = minder gevaarlijk dan JS-injectie) maar verdient ook aandacht.

### Scope-analyse

Vóór implementatie de omvang inventariseren:

```bash
# Hoeveel inline <script> tags zijn er in templates?
grep -r "<script" backend/templates/ | grep -v "src=" | wc -l

# Hoeveel onclick/onload/etc event handlers?
grep -rE "on(click|load|submit|change)=" backend/templates/ | wc -l
```

HTMX gebruikt `hx-*` attributen (geen inline handlers) — dat is al goed. Maar HTMX zelf heeft inline config nodig (`htmx.config`) en sommige HTMX-extensies gebruiken inline scripts.

### Aanpak (gefaseerd)

**Fase A — Inventarisatie (vereist vóór implementatie)**

1. Zoek alle inline `<script>` tags in templates
2. Categoriseer: HTMX-config, applicatielogica, derde partij
3. Beslissing per categorie: verplaatsen naar extern `.js`-bestand of nonce toevoegen

**Fase B — Nonce-infrastructuur in FastAPI**

```python
# Middleware: genereer een random nonce per request
import secrets

class CspNonceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce
        response = await call_next(request)
        # Vervang {nonce} placeholder in CSP header
        ...
```

De nonce moet beschikbaar zijn in Jinja2-templates via de request-context. Voeg toe aan `_context()`-helpers of als globale template-variabele via `sjablonen.env.globals`.

**Fase C — Templates updaten**

Elke inline `<script>` tag krijgt het nonce-attribuut:
```html
<script nonce="{{ csp_nonce }}">
  htmx.config.defaultSwapStyle = 'outerHTML';
</script>
```

Inline event handlers (`onclick=`, `onchange=`) verplaatsen naar aparte `.js`-bestanden in `static/js/`.

**Fase D — CSP aanpassen**

```python
_CSP_PRODUCTIE = (
    "default-src 'self'; "
    f"script-src 'self' 'nonce-{{nonce}}' https://unpkg.com; "
    "style-src 'self' 'unsafe-inline'; "  # stijlen kunnen apart behandeld worden
    ...
)
```

**Overwegingen:**
- `https://unpkg.com` (HTMX CDN) → overwegen HTMX lokaal te hosten in `static/js/`
- `'unsafe-inline'` voor styles mag blijven zolang er geen stijl-injectie-vector is
- HTMX `hx-on:` attribuut (HTMX 1.9+) telt niet als inline script → veilig

### Checklist

- [ ] Inventarisatie: `grep -r "<script" backend/templates/` uitvoeren, resultaat documenteren
- [ ] Beslissing: welke inline scripts naar extern `.js`, welke krijgen nonce
- [ ] `CspNonceMiddleware` implementeren (of nonce toevoegen aan `SecurityHeadersMiddleware`)
- [ ] Nonce beschikbaar maken in alle Jinja2-templates
- [ ] Alle inline `<script>` tags bijwerken met `nonce="{{ csp_nonce }}"`
- [ ] Inline event handlers (`onclick=`, etc.) inventariseren en verplaatsen
- [ ] HTMX lokaal hosten (verwijder `https://unpkg.com` uit CSP)
- [ ] CSP testen met browser-console op foutmeldingen
- [ ] Regressietest: HTMX-interacties (formulieren, partials, grid-bewerkingen)

---

## Item 4 — bcrypt auto-migratie + TOTP verplicht voor beheerders

**Ernst:** 🟢 Laag (bewuste backlog)
**Referentie:** App audit bevindingen 2.13 + 2.14

### 4a — bcrypt auto-migratie naar argon2

**Probleemstelling:**
Gebruikers met een legacy bcrypt-hash (gemigreerd uit v0.7) hebben een minder sterke hash. Na verificatie wordt de hash niet automatisch opgewaardeerd.

**Betrokken bestanden:**
- `backend/services/domein/auth_domein.py` (verificatielogica)
- `backend/services/auth_service.py` (login-flow)

**Aanpak:**

In `auth_domein.py` de verificatiefunctie splitsen in twee stappen:

```python
def verifieer_wachtwoord(wachtwoord: str, gehashed: str) -> tuple[bool, bool]:
    """Retourneert (geldig, moet_rehashen).

    moet_rehashen=True als het wachtwoord correct is maar de hash een
    legacy bcrypt-hash is die gemigreerd moet worden naar argon2.
    """
    if gehashed.startswith(_BCRYPT_PREFIXEN):
        geldig = _bcrypt.checkpw(wachtwoord.encode(), gehashed.encode())
        return geldig, geldig  # als correct → rehashen
    return _argon2.verify(wachtwoord, gehashed), False
```

In `auth_service.login()` na succesvolle verificatie:

```python
geldig, moet_rehashen = verifieer_wachtwoord(wachtwoord, gebruiker.wachtwoord_hash)
if geldig and moet_rehashen:
    gebruiker.wachtwoord_hash = hash_wachtwoord(wachtwoord)
    db.commit()
    logger.info("Wachtwoord van gebruiker %d gemigreerd van bcrypt naar argon2.", gebruiker.id)
```

**Migratietermijn:** Na go-live 3 maanden wachten, dan bcrypt-hashes deactiveren via `scripts/bcrypt_audit.py`.

**Checklist:**
- [ ] `verifieer_wachtwoord()` aanpassen: retourneert `(bool, bool)`
- [ ] `auth_service.login()` aanpassen: auto-rehashen indien `moet_rehashen`
- [ ] `auth_service.verifieer_wachtwoord_reset()` (als die bestaat) ook aanpassen
- [ ] Unit test: bcrypt-hash → na login → hash is argon2
- [ ] `scripts/bcrypt_audit.py` controleren: klaar voor gebruik na deadline

### 4b — TOTP verplicht voor beheerders

**Probleemstelling:**
Een beheerder of super_beheerder zonder TOTP ingesteld heeft geen 2FA. Bij een gelekt wachtwoord is directe toegang tot het beheerpaneel mogelijk.

**Aanpak:**

In `auth_service.login()`, na succesvolle wachtwoordverificatie maar vóór het uitsturen van het JWT-token:

```python
ROLLEN_MET_VERPLICHTE_TOTP = {"beheerder", "super_beheerder"}

# Haal de hoogste rol van de gebruiker op
rollen = {r.rol for r in gebruiker.rollen if r.is_actief}
totp_verplicht = bool(rollen & ROLLEN_MET_VERPLICHTE_TOTP)

if totp_verplicht and not gebruiker.totp_actief:
    # Stuur door naar TOTP-instelpagina met een tijdelijk token
    return {"stap": "totp_setup_vereist", "temp_token": ...}
```

In de auth-router: nieuwe stap `totp_setup_vereist` afhandelen — gebruiker komt na login direct op de TOTP-instelpagina terecht en kan de app niet gebruiken totdat TOTP is ingesteld.

**Aandachtspunten:**
- Bestaande beheerders zonder TOTP moeten bij de eerstvolgende login TOTP instellen — communiceer dit van tevoren
- De TOTP-instelpagina mag niet bereikbaar zijn zonder het tijdelijke token
- Na TOTP-instelling: normaal inloggen (stap 2)

**Checklist:**
- [ ] `ROLLEN_MET_VERPLICHTE_TOTP` constante definiëren in `auth_domein.py` of `config.py`
- [ ] Login-flow uitbreiden met `totp_setup_vereist` stap
- [ ] Tijdelijk token aanmaken voor TOTP-setup (apart `aud`-claim, bijv. `"totp_setup"`)
- [ ] Auth-router: `/auth/totp-setup-vereist` endpoint (geeft instelpagina terug met temp token)
- [ ] Beveiliging: TOTP-instelpagina vereist geldig `"totp_setup"` temp token
- [ ] Na TOTP-instelling: temp token ongeldig maken, normale login-flow hervatten
- [ ] i18n: nieuwe sleutels voor melding "TOTP is verplicht voor uw rol"
- [ ] Testen: beheerder zonder TOTP → wordt doorgestuurd naar instelpagina

---

## Volgorde van aanpak

| Prioriteit | Item | Afhankelijkheden |
|---|---|---|
| **Nu** | Item 1 — AuditLog | Geen |
| **Nu** | Item 2 — NAS firewall | Infrastructuur op NAS |
| **Volgende sprint** | Item 3 — CSP nonce | Fase A (inventarisatie) vereist eerst |
| **Backlog** | Item 4a — bcrypt migratie | Geen |
| **Backlog** | Item 4b — TOTP verplicht | Item 4a afronden eerst |

---

## Overige kleinere punten (niet in apart item)

Deze punten uit het auditrapport zijn klein genoeg voor een directe fix zonder apart plan:

| Punt | Bestand | Fix |
|---|---|---|
| Open redirect via Referer | `locaties.py:143-144` | `terug_pad` beperken tot vaste allowlist of altijd `/dashboard` |
| Foutmelding in redirect-URL | `account.py:88` | Vaste foutsleutel i.p.v. ruwe exception-string |
| Direct DB-query in router | `gebruikers.py:61,183` | Verplaatsen naar `GebruikerService` of `LocatieService` |
| JWT `rol` claim overbodig | `auth_domein.py:93` | Claim verwijderen uit token-payload |
| Security headers op static files | `main.py:61` | Verifiëren via live request; evt. middleware aanpassen |

Deze worden bij gelegenheid opgelost als ze tegenkomen bij andere werkzaamheden.
