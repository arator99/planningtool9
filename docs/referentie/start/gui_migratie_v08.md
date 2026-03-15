# v0.7 GUI Structuur - Migratie Referentie voor v0.8

Dit document bevat een complete analyse van de v0.7 GUI structuur voor migratie naar v0.8 (web).

---

## 1. SCHERMEN INVENTARISATIE

### 1.1 Alle Geregistreerde Schermen (22 schermen + login)

#### Dashboard & Kern Schermen

| Scherm | scherm_id | Rollen | Services | Bijzonderheden |
|--------|-----------|--------|----------|----------------|
| `Dashboard` | dashboard | alle | NotitieService, PlanningService, VerlofService, VerlofSaldoService | is_dashboard=True, volgorde=0 |
| `LoginScherm` | - | - | AuthenticatieService | NIET in registry, apart login flow |

#### Planning Schermen

| Scherm | scherm_id | Rollen | Services | Bijzonderheden |
|--------|-----------|--------|----------|----------------|
| `PlanningRoosterScherm` | planning | planner, beheerder, admin | ExportService, GebruikerService, InstellingenService, NotitieService, PlanningService, RodeLijnService, ShiftcodeService | volgorde=10, Mixins: AutoSchedulingMixin, FoutenPaneelMixin, GridDataMixin, NavigatieMixin |
| `MijnPlanningScherm` | mijn_planning | teamlid, planner, beheerder, admin | FeestdagenService, GebruikerService, NotitieService, PlanningService, RodeLijnService | volgorde=5, Read-only grid |

#### Verlof Schermen

| Scherm | scherm_id | Rollen | Services | Bijzonderheden |
|--------|-----------|--------|----------|----------------|
| `VerlofAanvraagScherm` | verlof_aanvraag | teamlid, planner, beheerder, admin | VerlofService, VerlofSaldoService | volgorde=20, extends BasisVerlofScherm |
| `VerlofGoedkeuringScherm` | verlof_goedkeuring | planner, beheerder, admin | GebruikerService, VerlofService | volgorde=21, extends BasisVerlofScherm |
| `VerlofOverzichtScherm` | verlof_overzicht | teamlid, planner, beheerder, admin | VerlofService | volgorde=22 |
| `VerlofSaldoBeheerScherm` | verlof_saldo_beheer | planner, beheerder, admin | VerlofSaldoService | volgorde=23, FIFO saldo beheer |
| `BasisVerlofScherm` | - | - | - | NIET in registry, parent class |

#### Personeels/Beheer Schermen

| Scherm | scherm_id | Rollen | Services | Bijzonderheden |
|--------|-----------|--------|----------|----------------|
| `PersoneelScherm` | personeel | planner, beheerder, admin | GebruikerService | volgorde=30, heeft scherm_menu |
| `GebruikerBeheerScherm` | gebruiker_beheer | planner, beheerder, admin | GebruikerService, PostService, TeamService, TeamKoppelingService, WerkpostKoppelingService | volgorde=35 |
| `TeamsBeheerScherm` | teams_beheer | planner, beheerder, admin | TeamService, TeamKoppelingService | volgorde=31 |
| `RechtenBeheerScherm` | rechten_beheer | beheerder, admin | SchermRechtenService | volgorde=51, DB rights overrides |

#### Configuratie Schermen

| Scherm | scherm_id | Rollen | Services | Bijzonderheden |
|--------|-----------|--------|----------|----------------|
| `InstellingenScherm` | instellingen | beheerder, admin | InstellingenService | volgorde=50 |
| `HRRegelsBeheerScherm` | hr_regels_beheer | beheerder, admin | HRRegelBeheerService | volgorde=53 |
| `LogboekScherm` | logboek | beheerder, admin | LogboekService, GebruikerService | volgorde=52, audit trail |

#### Data Beheer Schermen

| Scherm | scherm_id | Rollen | Services | Bijzonderheden |
|--------|-----------|--------|----------|----------------|
| `AlgemeneShiftcodesScherm` | algemene_shiftcodes | planner, beheerder, admin | ShiftcodeService | volgorde=31 |
| `TypetabellenScherm` | typetabellen | planner, beheerder, admin | PostService, TypetabelService | volgorde=32 |
| `WerkpostBeheerScherm` | werkposten_beheer | planner, beheerder, admin | PostService, GebruikerService, ShiftcodeService, WerkpostKoppelingService | volgorde=33 |
| `AdvBeheerScherm` | adv_beheer | planner, beheerder, admin | AdvService, GebruikerService | volgorde=36 |

#### Overige Schermen

| Scherm | scherm_id | Rollen | Services | Bijzonderheden |
|--------|-----------|--------|----------|----------------|
| `NotitieScherm` | berichten | teamlid, planner, beheerder, admin | NotitieService, GebruikerService | volgorde=25, Inbox/Verzonden tabs |
| `RapportenScherm` | rapporten | planner, beheerder, admin | ExportService, RapportService | volgorde=40 |
| `ShiftVoorkeurenScherm` | shift_voorkeuren | teamlid, planner, beheerder, admin | GebruikerService | volgorde=100, menu_categorie="_account" (verborgen) |

---

### 1.2 Scherm Inheritance Structuur

```
BasisScherm (src/gui/basis_scherm.py)
├── Dashboard
├── LoginScherm
├── PlanningRoosterScherm (+ 4 Mixins)
├── MijnPlanningScherm
├── NotitieScherm
├── PersoneelScherm
├── GebruikerBeheerScherm
├── RapportenScherm
├── RechtenBeheerScherm
├── HRRegelsBeheerScherm
├── InstellingenScherm
├── LogboekScherm
├── AdvBeheerScherm
├── AlgemeneShiftcodesScherm
├── TypetabellenScherm
├── WerkpostBeheerScherm
├── TeamsBeheerScherm
├── ShiftVoorkeurenScherm
├── VerlofOverzichtScherm
├── VerlofSaldoBeheerScherm
└── BasisVerlofScherm
    ├── VerlofAanvraagScherm
    └── VerlofGoedkeuringScherm
```

---

### 1.3 Lifecycle Hooks Per Scherm

| Hook | Schermen die het gebruiken | Doel |
|------|---------------------------|------|
| `on_screen_active()` | Dashboard, PersoneelScherm, NotitieScherm, alle VerlofSchermen, RapportenScherm, alle BeheerSchermen | Data refresh bij navigatie |
| `on_hide()` | PlanningRoosterScherm, MijnPlanningScherm | Cleanup (timers stoppen) |
| `on_before_show()` | Minimaal gebruikt | Pre-show state check |
| `get_scherm_menu()` | PersoneelScherm | Dynamische menu items |

---

## 2. SCHERMREGISTRY SYSTEEM

### 2.1 SchermRegistratie Dataclass

```python
@dataclass
class SchermRegistratie:
    scherm_id: str                          # Unieke ID (bijv. "dashboard")
    scherm_klasse: Type                     # Klasse referentie
    menu_naam: str                          # Menu label Nederlands
    toegang_rollen: List[str]              # ["teamlid", "planner", etc.]
    menu_categorie: Optional[str] = None   # None = top-level, anders submenu
    is_dashboard: bool = False             # Markering voor dashboard
    icon: Optional[str] = None             # Icon pad (ongebruikt)
    volgorde: int = 0                      # Sort order in menu
```

### 2.2 SchermRegistry Methodes

| Methode | Return Type | Beschrijving |
|---------|-------------|--------------|
| `get_scherm(scherm_id)` | SchermRegistratie | Haal registratie op |
| `has_scherm(scherm_id)` | bool | Bestaat scherm? |
| `registreer(registratie)` | void | Registreer nieuw scherm |
| `heeft_toegang(scherm_id, rol, gebruik_db=True)` | bool | Check toegang (incl. DB overrides) |
| `get_schermen_voor_rol(rol, gebruik_db=True)` | List[SchermRegistratie] | Alle schermen voor rol |
| `get_dashboard_voor_rol(rol, gebruik_db=True)` | SchermRegistratie | Dashboard voor rol |
| `get_menu_structuur(rol, gebruik_db=True)` | Dict[Optional[str], List] | Menu structuur |
| `get_alle_schermen()` | Dict[str, SchermRegistratie] | Alle schermen |

---

## 3. NAVIGATIE SYSTEEM

### 3.1 Architectuur Overzicht

```
NavigatieManager (Orchestrator)
    ├── NavigatieContext (Gedeelde State)
    │   ├── gebruiker_rol: str
    │   ├── scherm_cache: Dict[str, BasisScherm]
    │   ├── huidig_scherm_id: Optional[str]
    │   ├── geschiedenis: List[str]
    │   └── geschiedenis_index: int
    │
    ├── HistoryController (Browser-like navigatie)
    │   ├── kan_terug() → bool
    │   ├── kan_vooruit() → bool
    │   ├── ga_terug() → Optional[str]
    │   ├── ga_vooruit() → Optional[str]
    │   └── voeg_toe(scherm_id) → void
    │
    ├── ScreenController (Lifecycle management)
    │   ├── heeft_toegang(scherm_id) → bool
    │   ├── get_scherm(scherm_id, force_refresh) → BasisScherm
    │   ├── activeer_scherm(scherm, scherm_id) → void
    │   └── ververs_huidig_scherm() → void
    │
    └── MenuController (Menu management)
        ├── bouw_menu() → void
        └── update_scherm_menu(scherm) → void
```

### 3.2 NavigatieManager Hoofd Methodes

| Methode | Beschrijving |
|---------|--------------|
| `navigeer_naar(scherm_id, force_refresh=False, skip_dirty_check=False)` | Navigeer naar scherm |
| `ga_terug()` | Browser-like terug |
| `ga_vooruit()` | Browser-like vooruit |
| `ververs_huidig_scherm()` | Re-run on_screen_active() |
| `get_huidig_scherm_id()` | Huidige scherm ID |
| `haal_huidig_scherm()` | Huidige BasisScherm instance |

### 3.3 Navigatie Flow

```
navigeer_naar(scherm_id)
    │
    ├─ Check dirty state (vraag_opslaan_bij_navigatie)
    │   └─ Show 3-button dialog if dirty
    │
    ├─ Check access (heeft_toegang)
    │
    ├─ Get/create screen (get_scherm)
    │   └─ Lazy loading + caching
    │
    ├─ Activate screen (activeer_scherm)
    │   ├─ on_hide() op vorig scherm
    │   ├─ on_before_show()
    │   ├─ setCurrentWidget()
    │   ├─ on_screen_active()
    │   └─ on_after_show()
    │
    ├─ Update menu (update_scherm_menu)
    │
    └─ Update history (voeg_toe)
```

---

## 4. BASISSCHERM TEMPLATE

### 4.1 Template Method Pattern

```python
class BasisScherm(QWidget):
    def __init__(self):
        self._initialiseer_basis()  # Calls build_ui via template

    def build_ui(self, layout: QVBoxLayout) -> None:
        raise NotImplementedError  # Subclasses MUST override
```

### 4.2 Lifecycle Hooks

| Hook | Wanneer | Typisch gebruik |
|------|---------|-----------------|
| `on_before_show()` | Voor widget zichtbaar | State check, animaties |
| `on_screen_active()` | Bij navigatie | **Data refresh (HIER)** |
| `on_after_show()` | Na widget zichtbaar | Focus, scroll, UI finalisatie |
| `on_hide()` | Bij navigatie weg | Cleanup, timers stoppen |

### 4.3 Dirty State Tracking

| Methode | Beschrijving |
|---------|--------------|
| `heeft_onopgeslagen_wijzigingen()` | Override voor dirty tracking |
| `sla_wijzigingen_op()` | Save changes |
| `vraag_opslaan_bij_navigatie()` | 3-button dialog: Opslaan, Niet Opslaan, Annuleren |

### 4.4 Scherm Menu (Dynamisch)

```python
def get_scherm_menu() -> Optional[Tuple[str, List[Tuple[str, callable]]]]:
    # Return None: Geen menu
    # Return ("Menu Naam", [("Item 1", callback), ("Item 2", callback)])
    return None
```

### 4.5 Feedback Helpers

| Methode | Type | Beschrijving |
|---------|------|--------------|
| `toon_bericht(bericht, titel)` | Information | Groene melding |
| `toon_waarschuwing(bericht, titel)` | Warning | Gele melding |
| `toon_fout(bericht, titel)` | Critical | Rode melding |
| `bevestig_actie(vraag, titel)` | Question | Ja/Nee dialog → bool |
| `toon_inline_bericht(layout, bericht, type)` | Non-blocking | Label in UI |

### 4.6 UI Helpers

| Methode | Beschrijving |
|---------|--------------|
| `voeg_logo_toe(layout, grootte=80)` | Logo toevoegen |
| `voeg_invoerveld_toe(layout, label, placeholder, wachtwoord, min_hoogte)` | Input field |
| `stel_enter_actie_in(widget, methode)` | Enter key handler |

---

## 5. MENU STRUCTUUR

### 5.1 Top-Level Menus (categorie=None)

| Menu Item | volgorde | Scherm |
|-----------|----------|--------|
| Dashboard | 0 | dashboard |
| Berichten | 25 | berichten |
| Werkposten Beheer | 33 | werkposten_beheer |
| Algemene Shiftcodes | 31 | algemene_shiftcodes |
| Typetabellen | 32 | typetabellen |
| ADV Beheer | 36 | adv_beheer |
| Rapporten | 40 | rapporten |

### 5.2 Submenu Categorieën

#### Planning
| Menu Item | volgorde |
|-----------|----------|
| Mijn Planning | 5 |
| Planning | 10 |

#### Verlof
| Menu Item | volgorde |
|-----------|----------|
| Aanvragen | 20 |
| Behandelen | 21 |
| Overzicht | 22 |
| Saldo Beheer | 23 |

#### Personeelsbeheer
| Menu Item | volgorde |
|-----------|----------|
| Personeelsoverzicht | 30 |
| Teams Beheer | 31 |
| Gebruikersbeheer | 35 |

#### Instellingen
| Menu Item | volgorde |
|-----------|----------|
| Algemeen | 50 |
| Rechten Beheer | 51 |
| Logboek | 52 |
| HR Regels | 53 |

### 5.3 Speciale Menu's (Niet in Registry)

#### Help Menu
- Quick Start (F1)
- Algemene Handleiding
- Planner Handleiding (conditioneel)
- Beheerder Handleiding (conditioneel)
- Changelog

#### Account Menu (meest rechts)
- Shift Voorkeuren
- Wachtwoord Wijzigen
- Wissel naar Dark/Light Mode
- Uitloggen

---

## 6. DIALOGEN

### 6.1 Alle Dialogen

| Dialoog | Doel | Gebruikt door |
|---------|------|---------------|
| `WachtwoordWijzigenDialoog` | Wachtwoord wijzigen | Account Menu |
| `GridNotitieDialoog` | Notities aan planning cel | PlanningRoosterScherm |
| `PeriodeSelectieDialoog` | Rode lijn periode selectie | PlanningRoosterScherm |
| `ValidatieRapportDialoog` | HR validatie resultaten | PlanningRoosterScherm |
| `AdvToekenningDialoog` | ADV toekenning form | AdvBeheerScherm |
| `ShiftCodePickerDialoog` | Shiftcode selection | PlanningGrid |
| `OverrideDialoog` | Validatie override | PlanningGrid |
| `VerlofNamensDialoog` | Verlof namens medewerker | VerlofSchermen |

### 6.2 Dialog Pattern

```python
class SomeDialoog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dialog Title")
        self.setModal(True)
        self._init_ui()

    def exec(self) -> int:
        return super().exec()  # QDialog.Accepted of QDialog.Rejected

    def get_result(self) -> ResultType:
        # Extract data from widgets
        pass
```

### 6.3 Dialog Usage in Schermen

```python
dialoog = SomeDialoog(self)
if dialoog.exec() == QDialog.Accepted:
    data = dialoog.get_result()
    # Process data
```

---

## 7. SERVICES OVERZICHT

### 7.1 Service Categorieën

#### User Management
| Service | Beschrijving |
|---------|--------------|
| `GebruikerService` | User CRUD, roles, preferences |
| `PostService` | Position/post management |
| `TeamService` | Team management |
| `TeamKoppelingService` | Team assignments |
| `WerkpostKoppelingService` | Position assignments |

#### Planning
| Service | Beschrijving |
|---------|--------------|
| `PlanningService` | Shift loading, saving, validation |
| `RodeLijnService` | Red line periods, info |
| `ShiftcodeService` | Shiftcode CRUD + validation |
| `FeestdagenService` | Holiday info |
| `ExportService` | Excel/PDF export |

#### Leave Management
| Service | Beschrijving |
|---------|--------------|
| `VerlofService` | Leave requests (CRUD, status) |
| `VerlofSaldoService` | Leave balance (FIFO) |

#### Configuration
| Service | Beschrijving |
|---------|--------------|
| `InstellingenService` | Settings CRUD |
| `SchermRechtenService` | Screen access rights |
| `HRRegelBeheerService` | HR rule configuration |

#### Business Logic
| Service | Beschrijving |
|---------|--------------|
| `AdvService` | ADV allowances |
| `RotatieService` | Rotation scheduling |
| `SuggestieService` | Auto-complete suggestions |
| `KandidaatScoringService` | Auto-scheduling scoring |
| `AutoSchedulingService` | Full auto-scheduling |
| `BalansService` | Shift balance calculations |
| `RapportService` | Report generation |

#### Admin
| Service | Beschrijving |
|---------|--------------|
| `LogboekService` | Audit logging |
| `BackupService` | Database backups |
| `AuthenticatieService` | Login/password |

### 7.2 Service Architecture

```python
class SomeService:
    @staticmethod
    def methode_naam(param: Type) -> ReturnType:
        # Pure function logic (stateless)
        return result
```

**Regels:**
- Services zijn stateless
- Type hints verplicht
- Return domein objecten (dataclasses), geen dicts
- GUI importeert ALLEEN uit applicatie laag
- Exceptions worden gegooid, GUI vangt op

---

## 8. DATA FLOW PATTERNS

### 8.1 Typische Scherm Lifecycle

```
1. GUI instantieert Scherm (lazy loading)
   └─ build_ui(layout) → UI constructie (lege state)

2. NavigatieManager navigeert naar scherm
   ├─ on_before_show()
   ├─ setCurrentWidget()
   ├─ on_screen_active() → DATA LADEN HIER
   └─ on_after_show()

3. Gebruiker interactie
   ├─ Widgets bewerken
   ├─ Knop klikken → callback → service → database → result
   └─ (Dirty state tracking)

4. Navigatie weg
   ├─ vraag_opslaan_bij_navigatie() indien dirty
   └─ on_hide() → cleanup
```

### 8.2 Service Call Pattern

```python
try:
    result = SomeService.methode(params)
    self.toon_bericht(f"Succes: {result}")
except ValidatieFout as e:
    self.toon_waarschuwing(str(e))
except Exception as e:
    logger.error(f"Fout: {e}", exc_info=True)
    self.toon_fout("Kon actie niet uitvoeren")
```

---

## 9. STIJLEN & THEMA

### 9.1 Kleur Constanten

| Constante | Gebruik |
|-----------|---------|
| `Stijlen.ACHTERGROND` | Background |
| `Stijlen.TEKST_HOOFD` | Primary text |
| `Stijlen.TEKST_SUBTITEL` | Secondary text |
| `Stijlen.SUCCES` | Green (success) |
| `Stijlen.WAARSCHUWING` | Yellow (warning) |
| `Stijlen.FOUT` | Red (error) |
| `Stijlen.INFO` | Blue (info) |

### 9.2 Stijl Methodes

| Methode | Beschrijving |
|---------|--------------|
| `get_stylesheet()` | Full application stylesheet |
| `get_button_style(kleur)` | Button specific style |
| `get_dashboard_button_style(kleur)` | Dashboard button style |
| `get_message_style(type)` | Message styling |

### 9.3 Dark Mode

```python
ThemeManager.wissel_theme()  # Toggle theme → str (new theme)
ThemeManager.is_dark_mode()  # Check current → bool
```

**BELANGRIJK: Geen hardcoded kleuren!**
- ❌ `#ff0000`, `QColor("#3b82f6")`
- ✓ `Stijlen.FOUT`, `QColor(Stijlen.INFO)`

---

## 10. ARCHITECTUUR LAGENMODEL

```
┌─────────────────────────────────────────┐
│ GUI Layer (src/gui/)                     │
│ ├─ Schermen (BasisScherm subclasses)    │
│ ├─ Dialogen                             │
│ ├─ Widgets                              │
│ ├─ Navigatie (controllers)              │
│ └─ Stijlen (theme manager)              │
└─────────────────────────────────────────┘
         ↓ imports only from
┌─────────────────────────────────────────┐
│ Services Layer (src/services/applicatie/)│
│ ├─ Application services (stateless)     │
│ ├─ Re-exported domein objecten          │
│ └─ Exception types                      │
└─────────────────────────────────────────┘
         ↓ uses
┌─────────────────────────────────────────┐
│ Domein Layer (src/services/domein/)     │
│ ├─ Data structures (@dataclass)         │
│ ├─ Business rules (validators)          │
│ └─ Domain exceptions                    │
└─────────────────────────────────────────┘
         ↓ uses
┌─────────────────────────────────────────┐
│ Repository Layer (src/services/repo/)   │
│ ├─ SQL queries                          │
│ └─ Returns Dict[str, Any]               │
└─────────────────────────────────────────┘
         ↓ uses
┌─────────────────────────────────────────┐
│ Database (SQLite)                       │
└─────────────────────────────────────────┘
```

**Import Regels:**
- ❌ GUI importeert NOOIT direct uit domein
- ❌ GUI importeert NOOIT uit repo
- ✓ GUI importeert ALLEEN uit src/services/applicatie
- ❌ Domein importeert NOOIT uit repo
- ❌ SQL queries ALLEEN in repo laag

---

## 11. MIGRATIE MAPPING v0.7 → v0.8

| v0.7 Component | Locatie | v0.8 Equivalent | Aanpak |
|----------------|---------|-----------------|--------|
| BasisScherm + 22 subclasses | src/gui/schermen/ | Page components + API routes | Elke scherm → endpoint + component |
| NavigatieManager | src/gui/navigatie/ | URL routing + state | Vervang QStackedWidget |
| Services (35+) | src/services/applicatie/ | **Herbruikbaar** | Geen wijzigingen nodig |
| @dataclass | src/services/domein/ | Pydantic BaseModel | Directe conversie |
| QDialog subclasses | src/gui/dialogen/ | Modal components | Component-based |
| Custom PyQt widgets | src/gui/widgets/ | React/Vue components | Herbouwen |
| Stijlen class | src/gui/stijlen/ | CSS + design tokens | Theme systeem porteren |
| Lifecycle hooks | BasisScherm | useEffect in components | Zelfde pattern |
| MenuBar | src/gui/navigatie/ | Navigation component | Vervangen |
| ThemeManager | src/gui/stijlen/ | CSS media queries | Simpele port |

---

## 12. KRITIEKE BESTANDEN VOOR REFERENTIE

### Navigatie Systeem
- `src/gui/navigatie/navigatie_manager.py`
- `src/gui/navigatie/screen_controller.py`
- `src/gui/navigatie/history_controller.py`
- `src/gui/navigatie/menu_controller.py`
- `src/gui/navigatie/navigatie_context.py`
- `src/gui/navigatie/menu_balk.py`
- `src/kern/scherm_registry.py`

### Basis
- `src/gui/basis_scherm.py`
- `src/gui/stijlen/kleuren.py`
- `src/gui/stijlen/__init__.py`

### Meest Gebruikte Services
- `src/services/applicatie/planning_service.py`
- `src/services/applicatie/verlof_service.py`
- `src/services/applicatie/gebruiker_service.py`
- `src/services/applicatie/notitie_service.py`
- `src/services/applicatie/__init__.py` (re-exports)

### Hoofd Schermen
- `src/gui/schermen/dashboard.py`
- `src/gui/schermen/planning_rooster_scherm.py`
- `src/gui/schermen/mijn_planning_scherm.py`
- `src/gui/schermen/verlof/` (alle 4 schermen)
- `src/gui/schermen/__init__.py` (registry)

---

## 13. SCHERM FUNCTIONALITEIT DETAILS

### Dashboard
**Functionaliteit:**
- Welkomstbericht met gebruikersnaam
- Ongelezen notities teller + link
- Openstaande verlofaanvragen teller
- Verlof saldo overzicht (indien teamlid)
- Planning overzicht komende week
- Snelkoppelingen naar veelgebruikte schermen

**Data geladen:**
- Notities (ongelezen count)
- Verlofaanvragen (pending count)
- Verlof saldo (voor teamlid)
- Planning shifts (komende 7 dagen)

---

### PlanningRoosterScherm
**Functionaliteit:**
- Maandweergave planning grid
- Medewerker rijen, datum kolommen
- Shiftcode toewijzing per cel
- Rode lijn periode modus
- Auto-scheduling
- HR validatie met fouten paneel
- Export naar Excel/PDF
- Context menu (rechtermuisklik)
- Keyboard shortcuts (Ctrl+Z, etc.)

**Mixins:**
- `AutoSchedulingMixin` - Automatisch inplannen
- `FoutenPaneelMixin` - Validatiefouten tonen
- `GridDataMixin` - Data loading/saving
- `NavigatieMixin` - Maand navigatie

**Data geladen:**
- Alle medewerkers
- Shiftcodes
- Planning data voor maand
- Validatie status

---

### VerlofAanvraagScherm
**Functionaliteit:**
- Eigen aanvragen tabel
- Nieuwe aanvraag formulier:
  - Start/eind datum
  - Verloftype selectie
  - Opmerking
- Saldo overzicht met FIFO verdeling
- Annuleren van eigen aanvragen

**Data geladen:**
- Eigen verlofaanvragen
- Verlof saldo met FIFO details
- Verloftypes

---

### PersoneelScherm
**Functionaliteit:**
- Tabel met alle medewerkers
- Filters: rol, status, zoektekst
- Export naar Excel
- Scherm menu: "Medewerker Toevoegen", "Exporteer Lijst"

**get_scherm_menu():**
```python
return ("Personeel Acties", [
    ("Medewerker Toevoegen", self._nieuwe_medewerker),
    ("Exporteer Lijst", self._exporteer)
])
```

---

*Dit document is gegenereerd op basis van v0.7 codebase analyse en dient als complete referentie voor v0.8 migratie.*
