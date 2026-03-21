# NAS Security Audit — Synology 192.168.0.6
**Datum:** 2026-03-21
**Scope:** Synology NAS bereikbaar op 192.168.0.6, inclusief Planningtool-deployment
**Methodologie:** Actieve poortscanning + HTTP header-analyse + servicebanner inspectie

---

## 1. Samenvatting

De NAS heeft **drie hoog-ernstige bevindingen** die aandacht vereisen vóór of kort na productiedeployment.
Het meest urgent is dat de Planningtool draait in development-modus op een publiek bindend adres,
waardoor de CSP, HSTS en de seed-guard uitgeschakeld zijn. Poort 5000 (DSM HTTP) staat open
zonder redirect naar HTTPS, en SSH accepteert nog wachtwoordauthenticatie.

| Ernst | Aantal |
|---|---|
| 🔴 Kritiek | 0 |
| 🟠 Hoog | 3 |
| 🟡 Middel | 3 |
| 🟢 Laag | 3 |

---

## 2. Open poorten (scan resultaat)

| Poort | Dienst | Status | Opmerkingen |
|---|---|---|---|
| 22 | SSH | 🟠 Open | Wachtwoordauthenticatie actief |
| 80 | nginx (statisch) | 🟡 Open | Onbekende pagina, nginx uit 2019 |
| 443 | nginx (statisch) | 🟡 Open | Zelfde content als poort 80, geen redirect |
| 445 | SMB/CIFS | 🟡 Open | Windows bestandsdeling |
| 139 | NetBIOS | 🟡 Open | Oud SMB-protocol |
| 5000 | DSM HTTP | 🟠 Open | Admin panel, geen redirect naar HTTPS |
| 5001 | DSM HTTPS | ✅ Open | Versleuteld, correct |
| 6690 | Synology Drive | ✅ Open | Sync-dienst |
| 8000 | **Planningtool** | 🟠 Open | Rechtstreeks bereikbaar, development-modus |
| 21 | FTP | ✅ Gesloten | Goed |
| 23 | Telnet | ✅ Gesloten | Goed |
| 3306 | MySQL | ✅ Gesloten | Goed |
| 873 | rsync | ✅ Gesloten | Goed |

---

## 3. Bevindingen

### 3.1 Planningtool draait in development-modus (OMGEVING niet ingesteld)

**Ernst: 🟠 Hoog**

**Bewijs:**
```
HTTP/1.1 405 Method Not Allowed
server: uvicorn
x-content-type-options: nosniff
x-frame-options: DENY
referrer-policy: strict-origin-when-cross-origin
permissions-policy: camera=(), microphone=(), geolocation=()
# ONTBREEKT: Content-Security-Policy
# ONTBREEKT: Strict-Transport-Security
```

De response op poort 8000 toont géén `Content-Security-Policy` en géén `Strict-Transport-Security` header.
In de applicatiecode (`security_headers.py`) worden deze headers enkel toegevoegd als `omgeving != "development"`.
Dit betekent dat de `.env` op de NAS `OMGEVING` niet instelt op een productiewaarde,
of dat de waarde ontbreekt waardoor de default `"development"` actief is.

**Gevolgen:**
- XSS-aanvallen worden niet geblokkeerd door CSP
- HSTS is inactief — downgrade-aanvallen mogelijk als HTTPS niet afgedwongen wordt
- **De seed-guard is actief** in development-modus: als de database leeg is, wordt een admin-account aangemaakt
- OpenAPI-documentatie (`/api/docs`) is bereikbaar van op het LAN

**Oplossing:**
Stel in de `.env` op de NAS in:
```
OMGEVING=production
```
Herbouw daarna de container: `docker compose up -d --build app`

---

### 3.2 Planningtool rechtstreeks bereikbaar op LAN (poort 8000)

**Ernst: 🟠 Hoog**

**Bewijs:** Directe HTTP-responses op `192.168.0.6:8000` zonder Cloudflare-headers.

De app bindt op `0.0.0.0:8000` (zie `docker-compose.yml: ports: "8000:8000"`).
Dit betekent dat iedereen op het LAN de app rechtstreeks kan bereiken, buiten Cloudflare om.

**Gevolgen:**
- Aanvaller op het LAN kan `CF-Connecting-IP`-header vervalsen → rate limiter omzeilen
- Aanvaller kan de app benaderen zonder Cloudflare's DDoS-bescherming en access-filtering
- Geen HTTPS op directe LAN-verbinding → wachtwoorden en sessiecookies in klare tekst over het netwerk

**Oplossingen (kies één):**

*Optie A — Bind uitsluitend aan localhost (aanbevolen als Cloudflare daemon lokaal draait):*
In `docker-compose.yml`:
```yaml
ports:
  - "127.0.0.1:8000:8000"
```

*Optie B — Firewall-regel op NAS:*
Via DSM → Configuratiescherm → Beveiliging → Firewall: blokkeer inkomend verkeer op poort 8000
van alle bronnen behalve de Cloudflare Tunnel daemon (intern Docker-netwerk).

*Optie C — Docker intern netwerk (geen port binding):*
Verwijder de `ports`-sectie volledig en laat de Cloudflare daemon communiceren via het
interne Docker-netwerk. Dit vereist dat `cloudflared` in hetzelfde Docker-netwerk draait.

---

### 3.3 DSM HTTP-toegang op poort 5000 (geen HTTPS-redirect)

**Ernst: 🟠 Hoog**

**Bewijs:**
```
HTTP/1.1 200 OK  ← directe 200, geen redirect naar poort 5001
Server: nginx
```

Het DSM-beheerpaneel is bereikbaar via onversleuteld HTTP op poort 5000.
Inloggegevens voor de NAS-beheerder reizen in klare tekst over het netwerk.

**Oplossing:**
DSM → Configuratiescherm → Netwerk → DSM-instellingen:
- Schakel **"Doorsturen naar HTTPS"** in
- Overweeg HTTP (poort 5000) volledig **uit te schakelen** als alle clients HTTPS ondersteunen

---

### 3.4 SSH wachtwoordauthenticatie actief

**Ernst: 🟡 Middel**

**Bewijs:**
```
Permission denied (publickey,password).
```

SSH op poort 22 accepteert zowel wachtwoord als publickey-authenticatie.
Bij een gelekt of zwak wachtwoord is de NAS volledig compromitteerbaar via SSH.

**Oplossing:**
DSM → Configuratiescherm → Terminal & SNMP → Terminal:
1. Schakel over op uitsluitend **publickey-authenticatie**
2. Of schakel SSH volledig uit als het niet regelmatig nodig is
3. Als SSH nodig blijft: overweeg de standaardpoort te wijzigen (security by obscurity, maar reduceert brute-force ruis)

---

### 3.5 Poort 80/443 — Onbekende nginx-pagina (2019)

**Ernst: 🟡 Middel**

**Bewijs:**
```
Server: nginx
Last-Modified: Wed, 06 Nov 2019 17:48:50 GMT
Content-Length: 1474
```

Poort 80 en 443 serveren een statische HTML-pagina via nginx, aangemaakt in 2019.
Dit is waarschijnlijk een overgebleven standaardpagina van een oude packageinstallatie
(bijv. Web Station). De pagina is zichtbaar zonder authenticatie.

**Aanbevelingen:**
- Identificeer welke package deze pagina serveert (DSM → Pakketcentrum)
- Verwijder of schakel de service uit als deze niet meer gebruikt wordt
- Controleer of poort 80 of 443 via de Cloudflare Tunnel extern bereikbaar is

---

### 3.6 SMB/NetBIOS poorten open (445, 139)

**Ernst: 🟡 Middel**

Poorten 445 (SMB) en 139 (NetBIOS) staan open. Dit is normaal voor Synology NAS als
Windows-bestandsdeling gebruikt wordt. Het risico is afhankelijk van de firewall-configuratie.

**Aanbevelingen:**
- Verifieer via DSM → Firewall dat poorten 445/139 **niet extern bereikbaar** zijn
- Poort 139 (NetBIOS) is een oud protocol — schakel uit als SMBv2/v3 voldoende is
- Zorg dat SMB-signing actief is (DSM → Bestandsdiensten → SMB → Geavanceerd)

---

### 3.7 Synology DSM API-lijst zonder authenticatie

**Ernst: 🟢 Laag**

**Bewijs:** `http://192.168.0.6:5000/webapi/query.cgi?api=SYNO.API.Info&method=query&query=all`
retourneert een volledige lijst van alle beschikbare DSM API-endpoints zonder authenticatie.

Dit is standaard Synology-gedrag en niet direct oplosbaar. Het lekt wel informatie over
de geïnstalleerde packages en DSM-versie aan een aanvaller op het LAN.

**Aanbeveling:** Beperk LAN-toegang tot poort 5000/5001 tot de beheer-PC via DSM-firewall.

---

### 3.8 SSH gebruikt geen post-quantum sleuteluitwisseling

**Ernst: 🟢 Laag**

**Bewijs:**
```
WARNING: connection is not using a post-quantum key exchange algorithm.
The server may need to be upgraded.
```

De SSH-server op de NAS ondersteunt geen post-quantum sleuteluitwisseling.
Dit is op dit moment geen acuut risico, maar relevant voor langetermijnbeveiliging.

**Aanbeveling:** DSM bijhouden op de meest recente versie — Synology voegt PQ-ondersteuning
toe via DSM-updates.

---

### 3.9 Geen expliciete Docker-netwerken gedefinieerd

**Ernst: 🟢 Laag**

In `docker-compose.yml` zijn geen expliciete `networks` gedefinieerd. Alle containers
(db, migrate, app) communiceren via het standaard Docker-bridge-netwerk. Technisch
correct, maar met expliciete netwerken kan je de PostgreSQL-container isoleren zodat
hij alleen bereikbaar is voor de app-container en niet voor andere containers op de NAS.

**Aanbeveling:**
```yaml
networks:
  intern:
    driver: bridge

services:
  db:
    networks: [intern]
  app:
    networks: [intern]
```

---

## 4. Positieve bevindingen

- ✅ FTP (21), Telnet (23), MySQL (3306), rsync (873) zijn gesloten
- ✅ DSM HTTPS (poort 5001) actief
- ✅ Synology Drive (6690) enkel beschikbaar voor sync-clients
- ✅ PostgreSQL niet extern gepubliceerd (geen `ports` voor de `db`-container)
- ✅ SSH weigert verbindingen zonder correcte credentials (geen anonieme toegang)
- ✅ DSM heeft eigen security headers (X-Content-Type-Options, X-Frame-Options, CSP)

---

## 5. Prioriteitenlijst

### Onmiddellijk

1. **[🟠 Hoog]** Stel `OMGEVING=production` in de `.env` op de NAS in en herstart de app-container.
   Dit activeert CSP, HSTS en de seed-guard in één keer.

2. **[🟠 Hoog]** Bind poort 8000 aan `127.0.0.1` in `docker-compose.yml` zodat de app
   enkel via de Cloudflare Tunnel bereikbaar is en niet rechtstreeks via het LAN.

3. **[🟠 Hoog]** Schakel DSM HTTP-redirect in (poort 5000 → 5001) of zet poort 5000 uit.

### Kortetermijn

4. **[🟡 Middel]** Schakel SSH-wachtwoordauthenticatie uit; gebruik uitsluitend publickeys.

5. **[🟡 Middel]** Identificeer en verwijder de onbekende nginx-pagina op poort 80/443.

6. **[🟡 Middel]** Controleer firewall-regels voor SMB (445/139) — mogen niet extern bereikbaar zijn.

### Backlog

7. **[🟢 Laag]** Expliciete Docker-netwerken toevoegen in `docker-compose.yml`.

8. **[🟢 Laag]** DSM bijhouden voor SSH post-quantum ondersteuning.

---

## 6. Snelle fix: docker-compose.yml

Twee wijzigingen die items 1 + 2 oplossen op het deployment-niveau:

```yaml
# docker-compose.yml — productie NAS versie
services:
  app:
    ports:
      - "127.0.0.1:8000:8000"   # ← was "8000:8000" (LAN-bereikbaar)
    environment:
      OMGEVING: production       # ← of via .env: OMGEVING=production
```

Na deze wijziging:
- Poort 8000 enkel bereikbaar voor localhost (Cloudflare daemon)
- App activeert CSP + HSTS + seed-guard

---

*Rapport gegenereerd op 2026-03-21. Gescande poorten: 21, 22, 23, 80, 139, 443, 445, 873, 3306, 5000, 5001, 6690, 8000, 8080, 8443.*
