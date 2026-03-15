# GUI Components Referentie

**Versie:** 0.7.x
**Laatst bijgewerkt:** 2026-03-01
**Doel:** Complete referentie van alle GUI widgets, schermen, dialogen en patterns

> **Let op:** GUI wordt vervangen in v0.8 (HTMX/Jinja2). Zie `docs/voorstellen/Blueprint_v0.8.md`

---

## 📋 Inhoudsopgave

1. [Introductie](#introductie)
2. [Basis Architectuur](#basis-architectuur)
3. [BasisScherm Klasse](#basisscherm-klasse)
4. [Navigatie Framework](#navigatie-framework)
5. [Widgets](#widgets)
6. [Schermen](#schermen)
7. [Dialogen](#dialogen)
8. [Stijlen & Theming](#stijlen--theming)
9. [Common Patterns](#common-patterns)

---

## Introductie

### GUI Stack

De GUI laag is gebouwd met **PyQt6** en volgt deze principes:

```
Schermen (QWidget)
    ↓
Widgets (herbruikbaar)
    ↓
Services (Applicatie laag)
    ↓
Domein Objecten
```

### Locaties

- **Basis:** `src/gui/basis_scherm.py` - Template voor alle schermen
- **Schermen:** `src/gui/schermen/` - Volledige pagina views
- **Widgets:** `src/gui/widgets/` - Herbruikbare componenten
- **Dialogen:** `src/gui/dialogen/` - Modal popups
- **Stijlen:** `src/gui/stijlen.py` - QSS styling + kleuren
- **Main:** `src/gui/main.py` - Hoofd venster + navigatie

---

## Basis Architectuur

### Lego-Plan Principe

Alle schermen volgen het **Lego-Plan** patroon:

1. **Overerven** van `BasisScherm`
2. **Implementeer** `build_ui(layout: QVBoxLayout)`
3. **Gebruik** feedback helpers (`toon_bericht()`, `toon_fout()`, `bevestig_actie()`)
4. **Call** services, GEEN directe database access

### Template Method Pattern

```python
from src.gui.basis_scherm import BasisScherm
from PyQt6.QtWidgets import QVBoxLayout, QLabel

class MijnScherm(BasisScherm):
    def build_ui(self, layout: QVBoxLayout) -> None:
        """Verplicht - bouw UI hier."""
        # Layout al beschikbaar, voeg widgets toe
        label = QLabel("Hallo Wereld!")
        layout.addWidget(label)

    def on_screen_active(self) -> None:
        """Optioneel - refresh data bij navigatie."""
        self._laad_data()
```

---

## BasisScherm Klasse

**Locatie:** `src/gui/basis_scherm.py`

### Overerven

```python
class BasisScherm(QWidget):
    """Basisklasse voor alle schermen."""
```

**Alle schermen MOETEN** erven van `BasisScherm`.

### Verplichte Method: `build_ui()`

```python
def build_ui(self, layout: QVBoxLayout) -> None:
    """
    Bouw UI componenten.
    Layout is al geïnitialiseerd met:
    - Margins: 24px all sides
    - Spacing: 16px tussen widgets
    - Alignment: Top

    Args:
        layout: QVBoxLayout waar widgets aan toegevoegd worden
    """
```

**Voorbeeld:**
```python
def build_ui(self, layout: QVBoxLayout) -> None:
    # Voeg titel toe
    titel = QLabel("Mijn Scherm")
    layout.addWidget(titel)

    # Voeg knop toe
    knop = QPushButton("Klik Mij")
    knop.clicked.connect(self._on_knop_klik)
    layout.addWidget(knop)
```

---

### Helper Methods

#### `voeg_logo_toe()`

```python
def voeg_logo_toe(
    self,
    layout: QVBoxLayout,
    grootte: int = 80
) -> None:
    """
    Voeg applicatie logo toe.

    Args:
        layout: Layout waar logo aan toegevoegd wordt
        grootte: Grootte in pixels (vierkant)
    """
```

**Gebruik:**
```python
def build_ui(self, layout: QVBoxLayout) -> None:
    self.voeg_logo_toe(layout, grootte=100)
```

---

#### `voeg_invoerveld_toe()`

```python
def voeg_invoerveld_toe(
    self,
    layout: QVBoxLayout,
    label_text: str,
    placeholder: str = "",
    wachtwoord: bool = False,
    min_hoogte: int = 40
) -> QLineEdit:
    """
    Voeg label + invoerveld paar toe.

    Args:
        layout: Target layout
        label_text: Tekst boven veld
        placeholder: Placeholder in veld
        wachtwoord: Password mode (asterisks)
        min_hoogte: Min hoogte veld

    Returns:
        QLineEdit widget voor verdere configuratie
    """
```

**Gebruik:**
```python
def build_ui(self, layout: QVBoxLayout) -> None:
    # Normaal veld
    self.naam_veld = self.voeg_invoerveld_toe(
        layout,
        label_text="Naam:",
        placeholder="Voer uw naam in"
    )

    # Wachtwoord veld
    self.wachtwoord_veld = self.voeg_invoerveld_toe(
        layout,
        label_text="Wachtwoord:",
        wachtwoord=True
    )
```

---

#### `stel_enter_actie_in()`

```python
def stel_enter_actie_in(
    self,
    widget: QLineEdit,
    methode: Callable
) -> None:
    """
    Bind Enter key op invoerveld aan actie.

    Args:
        widget: QLineEdit widget
        methode: Callback methode (zonder parameters)
    """
```

**Gebruik:**
```python
def build_ui(self, layout: QVBoxLayout) -> None:
    invoer = self.voeg_invoerveld_toe(layout, "Zoeken:")

    # Enter triggert zoek actie
    self.stel_enter_actie_in(invoer, self._zoek)

def _zoek(self) -> None:
    zoekterm = self.zoek_veld.text()
    # ... zoek logica
```

---

### Lifecycle Hooks

#### `on_screen_active()`

```python
def on_screen_active(self) -> None:
    """
    Wordt aangeroepen bij navigatie naar dit scherm.
    **Gebruik:** Data refreshing, state updates.
    """
```

**KRITIEK:** Dit is de **belangrijkste hook** voor data laden!

**Gebruik:**
```python
def on_screen_active(self) -> None:
    """Refresh data bij elke navigatie."""
    self._laad_gebruikers()
    self._update_badge()
```

---

#### `on_before_show()` / `on_after_show()` / `on_hide()`

```python
def on_before_show(self) -> None:
    """Vlak voor scherm zichtbaar wordt."""

def on_after_show(self) -> None:
    """Nadat scherm zichtbaar is (gebruik voor focus)."""

def on_hide(self) -> None:
    """Wanneer scherm verborgen wordt (cleanup)."""
```

**Gebruik:**
```python
def on_after_show(self) -> None:
    """Focus op eerste veld."""
    self.naam_veld.setFocus()

def on_hide(self) -> None:
    """Stop timer bij verlaten scherm."""
    if hasattr(self, '_timer'):
        self._timer.stop()
```

---

#### `get_scherm_menu()`

```python
def get_scherm_menu(self) -> Optional[Tuple[str, List[Tuple[str, callable]]]]:
    """
    Retourneer scherm-specifiek menu voor menubalk.

    Returns:
        None: Geen scherm-menu (bijv. Dashboard)
        Tuple: (menu_naam, menu_items)
            - menu_naam: "Planning Acties"
            - menu_items: [("Exporteer", self._exporteer), ...]
    """
```

**Gebruik:**
```python
def get_scherm_menu(self):
    return ("Planning Acties", [
        ("Exporteer naar Excel", self._exporteer),
        ("Valideer Planning", self._valideer),
        ("Publiceer Planning", self._publiceer)
    ])
```

**Effect:** Menu verschijnt/verdwijnt automatisch bij navigatie.

---

### Feedback Helpers

#### `toon_bericht()` (NIET geïmplementeerd in BasisScherm)

**LET OP:** Deze methode moet geïmplementeerd worden in `MainWindow` of als mixin.

**Pattern:**
```python
def toon_bericht(self, titel: str, bericht: str) -> None:
    """Toon succes/info bericht."""
    QMessageBox.information(self, titel, bericht)

def toon_fout(self, titel: str, fout: str) -> None:
    """Toon fout bericht."""
    QMessageBox.warning(self, titel, fout)

def bevestig_actie(self, titel: str, vraag: str) -> bool:
    """Vraag bevestiging."""
    reply = QMessageBox.question(
        self, titel, vraag,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    return reply == QMessageBox.StandardButton.Yes
```

---

## Navigatie Framework

**Doel:** Plugin architectuur voor scherm registratie zonder main.py aan te passen.

### SchermRegistry (in main.py)

**NOOIT direct schermen toevoegen aan main.py** - gebruik SchermRegistry.

#### SchermRegistratie

```python
@dataclass
class SchermRegistratie:
    scherm_id: str              # "gebruiker_beheer"
    scherm_klasse: Type         # GebruikerBeheerScherm
    menu_naam: str              # "Gebruikers Beheren"
    toegang_rollen: List[str]   # ["admin", "beheerder"]
    menu_categorie: Optional[str] = None  # None = top-level
    is_dashboard: bool = False
    volgorde: int = 50          # Positie (0-100)
```

#### Registratie Pattern

**Locatie:** `src/gui/schermen/__init__.py`

```python
from ..scherm_registry import SchermRegistry, SchermRegistratie
from .mijn_scherm import MijnScherm

# Registreer scherm
SchermRegistry.registreer(SchermRegistratie(
    scherm_id="mijn_scherm",
    scherm_klasse=MijnScherm,
    menu_naam="Mijn Scherm",
    toegang_rollen=["planner", "admin"],
    menu_categorie=None,
    is_dashboard=False,
    volgorde=50
))
```

---

### Menu Categorieën (Submenu's)

Schermen kunnen gegroepeerd worden onder submenu's via `menu_categorie`:

| menu_categorie | Submenu Items | Beschrijving |
|----------------|---------------|--------------|
| `None` | - | Top-level menu item |
| `"Verlof"` | Aanvragen, Behandelen, Overzicht | Verlof functionaliteit |
| `"Personeelsbeheer"` | Personeelsoverzicht, Gebruikersbeheer | Personeel management |

**Voorbeeld: Submenu registratie**

```python
# Verlof submenu
SchermRegistry.registreer(SchermRegistratie(
    scherm_id="verlof_aanvraag",
    scherm_klasse=VerlofAanvraagScherm,
    menu_naam="Aanvragen",
    toegang_rollen=["teamlid", "planner", "beheerder", "admin"],
    menu_categorie="Verlof",  # Submenu onder "Verlof"
    volgorde=20
))

SchermRegistry.registreer(SchermRegistratie(
    scherm_id="verlof_goedkeuring",
    scherm_klasse=VerlofGoedkeuringScherm,
    menu_naam="Behandelen",
    toegang_rollen=["planner", "beheerder", "admin"],
    menu_categorie="Verlof",  # Submenu onder "Verlof"
    volgorde=21
))

SchermRegistry.registreer(SchermRegistratie(
    scherm_id="verlof_overzicht",
    scherm_klasse=VerlofOverzichtScherm,
    menu_naam="Overzicht",
    toegang_rollen=["teamlid", "planner", "beheerder", "admin"],
    menu_categorie="Verlof",  # Submenu onder "Verlof"
    volgorde=22
))

# Personeelsbeheer submenu
SchermRegistry.registreer(SchermRegistratie(
    scherm_id="personeel",
    scherm_klasse=PersoneelScherm,
    menu_naam="Personeelsoverzicht",
    toegang_rollen=["planner", "beheerder", "admin"],
    menu_categorie="Personeelsbeheer",
    volgorde=30
))

SchermRegistry.registreer(SchermRegistratie(
    scherm_id="gebruiker_beheer",
    scherm_klasse=GebruikerBeheerScherm,
    menu_naam="Gebruikersbeheer",
    toegang_rollen=["planner", "beheerder", "admin"],
    menu_categorie="Personeelsbeheer",
    volgorde=35
))
```

---

### Lazy Loading

**Schermen worden pas gecreëerd bij eerste navigatie**, daarna gecached.

**Voordeel:**
- Snelle startup
- Geheugen efficiënt
- Parallel development (geen merge conflicts)

---

### Rol-Gebaseerde Toegang

**SchermRegistry filtert automatisch** op gebruikersrol:

```python
# Admin ziet alle schermen
# Planner ziet alleen schermen met 'planner' in toegang_rollen
# Teamlid ziet alleen basis schermen
```

**Voorbeeld:**
```python
SchermRegistratie(
    scherm_id="gebruiker_beheer",
    scherm_klasse=GebruikerBeheerScherm,
    menu_naam="Gebruikers Beheren",
    toegang_rollen=["admin", "beheerder"],  # Alleen admin + beheerder
    volgorde=10
)
```

---

### Volledig Voorbeeld

**Nieuw scherm toevoegen (3 stappen):**

**1. Creëer scherm:** `src/gui/schermen/rapport_scherm.py`
```python
from ..basis_scherm import BasisScherm
from PyQt6.QtWidgets import QVBoxLayout, QLabel

class RapportScherm(BasisScherm):
    def build_ui(self, layout: QVBoxLayout) -> None:
        titel = QLabel("Rapporten")
        layout.addWidget(titel)

    def on_screen_active(self) -> None:
        # Refresh data
        self._laad_rapporten()

    def get_scherm_menu(self):
        return ("Rapport Acties", [
            ("Genereer Rapport", self._genereer)
        ])
```

**2. Registreer in** `src/gui/schermen/__init__.py`
```python
from ..scherm_registry import SchermRegistry, SchermRegistratie
from .rapport_scherm import RapportScherm

SchermRegistry.registreer(SchermRegistratie(
    scherm_id="rapporten",
    scherm_klasse=RapportScherm,
    menu_naam="Rapporten",
    toegang_rollen=["planner", "beheerder", "admin"],
    volgorde=60
))
```

**3. Done!** - Scherm verschijnt automatisch in menu voor juiste rollen.

---

## Widgets

### NotitieWidget

**Locatie:** `src/gui/widgets/notitie_widget.py`

**Doel:** Herbruikbare widget voor notities weergave met badge.

```python
class NotitieWidget(QWidget):
    # Signals
    notitie_gelezen = pyqtSignal(int)      # notitie_id
    notitie_verwijderd = pyqtSignal(int)
    notitie_aangemaakt = pyqtSignal(int)
```

#### Constructor

```python
def __init__(
    self,
    parent: Optional[QWidget] = None,
    toon_nieuwe_knop: bool = True,
    alleen_ongelezen: bool = False
)
```

**Parameters:**
- `toon_nieuwe_knop`: Toon "Nieuwe Notitie" knop
- `alleen_ongelezen`: Filter op ongelezen

#### Methods

```python
def refresh(self) -> None:
    """Ververs notities lijst."""
```

**Gebruik:**
```python
# In scherm
from src.gui.widgets.notitie_widget import NotitieWidget

def build_ui(self, layout):
    self.notitie_widget = NotitieWidget(
        parent=self,
        alleen_ongelezen=True
    )
    layout.addWidget(self.notitie_widget)

    # Connect signals
    self.notitie_widget.notitie_gelezen.connect(self._on_notitie_gelezen)

def on_screen_active(self):
    # Refresh bij navigatie
    self.notitie_widget.refresh()
```

---

### HRAlertPanel

**Locatie:** `src/gui/widgets/hr_alert_panel.py`

**Doel:** Side panel voor HR-validatie overtredingen.

```python
class HRAlertPanel(QWidget):
    # Signal: gebruiker klikt op overtreding
    cel_geselecteerd = pyqtSignal(str, int)  # (datum, medewerker_id)
```

#### Methods

```python
def update_alerts(self, rapport: ValidatieRapport) -> None:
    """
    Update overtredingen lijst.

    Args:
        rapport: ValidatieRapport van HRValidatieService
    """
```

**Gebruik:**
```python
from src.gui.widgets.hr_alert_panel import HRAlertPanel
from src.services.applicatie.hr_validatie_service import HRValidatieService

def build_ui(self, layout):
    # Splitter voor grid + alert panel
    splitter = QSplitter(Qt.Orientation.Horizontal)

    # Planning grid (70%)
    splitter.addWidget(self.planning_grid)

    # Alert panel (30%)
    self.hr_alert_panel = HRAlertPanel()
    self.hr_alert_panel.cel_geselecteerd.connect(self._navigeer_naar_cel)
    splitter.addWidget(self.hr_alert_panel)

    splitter.setStretchFactor(0, 7)
    splitter.setStretchFactor(1, 3)

    layout.addWidget(splitter)

def _valideer_planning(self):
    # Valideer maand
    rapport = HRValidatieService.valideer_maandplanning(self.jaar, self.maand)

    # Update panel
    self.hr_alert_panel.update_alerts(rapport)
```

---

### InfoCard

**Locatie:** `src/gui/widgets/info_card.py`

**Doel:** Card widget voor dashboard metrics.

```python
def __init__(
    self,
    titel: str,
    waarde: str,
    icoon: Optional[str] = None,
    kleur: str = "#2563eb"
)
```

**Gebruik:**
```python
from src.gui.widgets.info_card import InfoCard

def build_ui(self, layout):
    # Metrics row
    metrics_layout = QHBoxLayout()

    card1 = InfoCard("Actieve Gebruikers", "42", kleur="#10b981")
    card2 = InfoCard("Planning Items", "248", kleur="#3b82f6")
    card3 = InfoCard("Openstaande Verlofaanvragen", "7", kleur="#f59e0b")

    metrics_layout.addWidget(card1)
    metrics_layout.addWidget(card2)
    metrics_layout.addWidget(card3)

    layout.addLayout(metrics_layout)
```

---

### AlertWidget

**Locatie:** `src/gui/widgets/alert_widget.py`

**Doel:** Inline alert banners (info, success, warning, error).

```python
def __init__(
    self,
    bericht: str,
    type: str = "info"  # "info", "success", "warning", "error"
)
```

**Gebruik:**
```python
from src.gui.widgets.alert_widget import AlertWidget

def build_ui(self, layout):
    # Toon waarschuwing
    alert = AlertWidget(
        "Let op: Planning nog niet gepubliceerd!",
        type="warning"
    )
    layout.addWidget(alert)
```

---

## Schermen

### Scherm Overzicht

| Scherm | Bestand | Rol Toegang | Menu | Doel |
|--------|---------|-------------|------|------|
| **Dashboard** | `dashboard.py` | Alle | Top-level | Centraal overzicht per rol |
| **Login** | `login_scherm.py` | Publiek | - | Authenticatie |
| **Planning** | `planning_scherm.py` | planner+ | Top-level | Maandplanning grid |
| **Verlof Aanvraag** | `verlof_aanvraag_scherm.py` | Alle | Verlof → Aanvragen | Eigen verlofaanvragen beheren |
| **Verlof Goedkeuring** | `verlof_goedkeuring_scherm.py` | planner+ | Verlof → Behandelen | Verlofaanvragen goedkeuren/weigeren |
| **Verlof Overzicht** | `verlof_overzicht_scherm.py` | Alle | Verlof → Overzicht | Grid overzicht alle verlofaanvragen |
| **Personeel** | `personeel_scherm.py` | planner+ | Personeelsbeheer → Personeelsoverzicht | Medewerker overzicht |
| **Gebruiker Beheer** | `gebruiker_beheer_scherm.py` | planner+ | Personeelsbeheer → Gebruikersbeheer | CRUD gebruikers |
| **Typetabellen** | `typetabellen_scherm.py` | beheerder+ | Top-level | Referentiedata CRUD |
| **Werkposten Beheer** | `werkposten_beheer_scherm.py` | planner+ | Top-level | Werkpost en shift configuratie |
| **Rechten Beheer** | `rechten_beheer_scherm.py` | beheerder+ | Top-level | Scherm toegang config |
| **Rapporten** | `rapporten_scherm.py` | planner+ | Top-level | Rapporten genereren |

---

### GebruikerBeheerScherm (voorbeeld)

**Locatie:** `src/gui/schermen/gebruiker_beheer_scherm.py`

#### Functionaliteit

- Tabel met alle gebruikers (search + filter)
- CRUD operaties (Create, Read, Update, Delete)
- Rol assignment
- Activatie/Deactivatie

#### Key Methods

```python
def build_ui(self, layout: QVBoxLayout) -> None:
    """Bouw tabel + knoppen."""

def on_screen_active(self) -> None:
    """Refresh gebruikers lijst."""
    self._laad_gebruikers()

def _laad_gebruikers(self) -> None:
    """Haal gebruikers via service."""
    try:
        gebruikers = GebruikerService.haal_alle_gebruikers()
        self._vul_tabel(gebruikers)
    except Exception as e:
        self.toon_fout("Fout", str(e))

def _on_toevoegen(self) -> None:
    """Open dialoog voor nieuwe gebruiker."""

def _on_bewerken(self) -> None:
    """Open dialoog voor bewerken."""

def _on_verwijderen(self) -> None:
    """Deactiveer gebruiker (soft delete)."""
```

---

### PlanningScherm (voorbeeld)

**Locatie:** `src/gui/schermen/planning_scherm.py`

#### Functionaliteit

- **Grid** met 31 dagen × N medewerkers
- Shift codes in cellen (drag & drop / click edit)
- **HR-validatie integratie** (HRAlertPanel)
- **Override dialoog** bij CRITICAL overtredingen
- Publiceren naar medewerkers

#### Key Methods

```python
def build_ui(self, layout: QVBoxLayout) -> None:
    """Bouw maand selector + grid + alert panel."""

def on_screen_active(self) -> None:
    """Refresh planning + valideer."""
    self._laad_planning()
    self._valideer_planning()

def _laad_planning(self) -> None:
    """Haal planning via PlanningService."""
    planning = PlanningService.haal_maand_planning(self.jaar, self.maand)
    self._vul_grid(planning)

def _valideer_planning(self) -> None:
    """Run HR-validatie en update alert panel."""
    rapport = HRValidatieService.valideer_maandplanning(
        self.jaar,
        self.maand,
        force_refresh=True
    )
    self.hr_alert_panel.update_alerts(rapport)

def _on_opslaan(self) -> None:
    """Sla wijzigingen op, check CRITICAL overtredingen."""
    # Check CRITICAL
    critical = self.huidige_rapport.filter_op_ernst("CRITICAL")
    if critical:
        # Toon override dialoog
        dialog = OverrideDialoog(critical, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return  # Geannuleerd

        # Registreer overrides
        reden = dialog.get_reden()
        for overtreding in critical:
            HRValidatieService.registreer_override(...)

    # Sla op
    PlanningService.sla_planning_op_bulk(self.shifts)
    self.toon_bericht("Succes", "Planning opgeslagen")
```

---

## Dialogen

### OverrideDialoog

**Locatie:** `src/gui/dialogen/override_dialoog.py`

**Doel:** Modal dialoog voor CRITICAL HR-overtreding overrides.

```python
class OverrideDialoog(QDialog):
    def __init__(
        self,
        overtredingen: List[RegelOvertreding],
        parent: Optional[QWidget] = None
    )
```

#### Functionaliteit

- Toon lijst met CRITICAL overtredingen
- **Verplichte reden** (min 10 karakters)
- Validatie voor lege/korte reden
- Return reden via `get_reden()`

#### Gebruik

```python
from src.gui.dialogen.override_dialoog import OverrideDialoog

critical = rapport.filter_op_ernst("CRITICAL")
if critical:
    dialog = OverrideDialoog(critical, self)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        reden = dialog.get_reden()
        # Registreer overrides met reden
```

---

## Stijlen & Theming

### Stijlen Klasse

**Locatie:** `src/gui/stijlen.py`

#### Kleuren Constanten

```python
class Stijlen:
    # Kleuren (light mode default)
    PRIMAIR = "#2563eb"
    SUCCES = "#10b981"
    WAARSCHUWING = "#f59e0b"
    FOUT = "#ef4444"
    ACHTERGROND = "#ffffff"
    TEKST = "#0f172a"
    RAND = "#e2e8f0"
    # ... meer kleuren
```

**Gebruik:**
```python
from src.gui.stijlen import Stijlen

knop = QPushButton("Opslaan")
knop.setStyleSheet(f"""
    QPushButton {{
        background-color: {Stijlen.PRIMAIR};
        color: white;
        border-radius: 4px;
        padding: 8px 16px;
    }}
    QPushButton:hover {{
        background-color: {Stijlen.PRIMAIR_HOVER};
    }}
""")
```

---

#### `get_stylesheet()`

```python
@classmethod
def get_stylesheet(cls) -> str:
    """
    Retourneer volledige QSS stylesheet.
    Bevat styling voor alle Qt widgets.
    """
```

**Gebruik:**
```python
# In scherm __init__
self.setStyleSheet(Stijlen.get_stylesheet())

# Of: applicatie-breed in main.py
app = QApplication(sys.argv)
app.setStyleSheet(Stijlen.get_stylesheet())
```

---

#### Dynamic Properties (HR-validatie)

**QSS ondersteunt dynamic properties** voor context-aware styling:

```python
# Set property op widget
widget.setProperty("hr_status", "critical")

# Force style refresh
widget.setStyle(widget.style())
```

**QSS:**
```css
QWidget[hr_status="ok"] {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
}

QWidget[hr_status="warning"] {
    background-color: #fef3c7;
    border: 2px solid #f59e0b;
}

QWidget[hr_status="critical"] {
    background-color: #ffebee;
    border: 2px solid #ef5350;
}
```

---

### Theme Switching

**Light/Dark mode support:**

```python
class Theme(str, Enum):
    LIGHT = 'light'
    DARK = 'dark'

class Stijlen:
    LIGHT = {...}  # Light kleuren
    DARK = {...}   # Dark kleuren

    @classmethod
    def set_theme(cls, theme: Theme) -> None:
        """Switch tussen light en dark mode."""
```

**Gebruik:**
```python
from src.gui.stijlen import Stijlen, Theme

# Switch naar dark mode
Stijlen.set_theme(Theme.DARK)

# Refresh stylesheet
app.setStyleSheet(Stijlen.get_stylesheet())
```

---

## Common Patterns

### 1. CRUD Scherm Pattern

**Typische structuur voor CRUD schermen:**

```python
class CRUDScherm(BasisScherm):
    def build_ui(self, layout: QVBoxLayout) -> None:
        # Header met zoek + filter
        header_layout = QHBoxLayout()
        self.zoek_veld = QLineEdit()
        self.zoek_veld.textChanged.connect(self._filter_tabel)
        header_layout.addWidget(self.zoek_veld)
        layout.addLayout(header_layout)

        # Tabel
        self.tabel = QTableWidget()
        self.tabel.itemSelectionChanged.connect(self._on_selectie_gewijzigd)
        layout.addWidget(self.tabel)

        # Footer met CRUD knoppen
        footer_layout = QHBoxLayout()
        self.toevoegen_btn = QPushButton("Toevoegen")
        self.toevoegen_btn.clicked.connect(self._on_toevoegen)
        footer_layout.addWidget(self.toevoegen_btn)

        self.bewerken_btn = QPushButton("Bewerken")
        self.bewerken_btn.clicked.connect(self._on_bewerken)
        self.bewerken_btn.setEnabled(False)
        footer_layout.addWidget(self.bewerken_btn)

        self.verwijderen_btn = QPushButton("Verwijderen")
        self.verwijderen_btn.clicked.connect(self._on_verwijderen)
        self.verwijderen_btn.setEnabled(False)
        footer_layout.addWidget(self.verwijderen_btn)

        layout.addLayout(footer_layout)

    def on_screen_active(self) -> None:
        self._laad_data()

    def _laad_data(self) -> None:
        try:
            items = Service.haal_alle_items()
            self._vul_tabel(items)
        except Exception as e:
            self.toon_fout("Fout", str(e))

    def _on_selectie_gewijzigd(self) -> None:
        heeft_selectie = len(self.tabel.selectedItems()) > 0
        self.bewerken_btn.setEnabled(heeft_selectie)
        self.verwijderen_btn.setEnabled(heeft_selectie)
```

---

### 2. Signal/Slot Pattern

**Connect widget signals aan methodes:**

```python
# Button click
knop.clicked.connect(self._on_knop_klik)

# Text changed
invoer.textChanged.connect(self._on_text_gewijzigd)

# Item selection
tabel.itemSelectionChanged.connect(self._on_selectie)

# Custom signal (van widget)
widget.data_geladen.connect(self._on_data_geladen)
```

**KRITIEK:** Gebruik **lambda ALLEEN voor simpele expressies**:

```python
# ✅ OK: simpel
knop.clicked.connect(lambda: self.verwijder_item(item_id))

# ❌ VERBODEN: complexe logica
knop.clicked.connect(lambda: (
    self.valideer(),
    self.opslaan() if self.is_geldig else self.toon_fout("Fout"),
    self.refresh()
))

# ✅ CORRECT: gebruik benoemde methode
knop.clicked.connect(self._on_opslaan)

def _on_opslaan(self):
    if not self.valideer():
        self.toon_fout("Validatie Fout", "...")
        return
    self.opslaan()
    self.refresh()
```

---

### 3. Try/Except Pattern

**Service calls altijd wrappen:**

```python
def _laad_data(self) -> None:
    try:
        # Service call
        data = Service.haal_data()

        # Verwerk resultaat
        self._vul_ui(data)

    except ValueError as e:
        # Validatie fout
        self.toon_fout("Validatie Fout", str(e))

    except Exception as e:
        # Onverwachte fout
        logger.error(f"Fout bij laden data: {e}", exc_info=True)
        self.toon_fout("Fout", "Er ging iets mis. Probeer opnieuw.")
```

---

### 4. Feedback Pattern

**Gebruiker feedback na acties:**

```python
def _on_opslaan(self) -> None:
    try:
        # Valideer
        if not self._valideer():
            return

        # Opslaan
        Service.sla_op(self._get_data())

        # ✅ Succes feedback
        self.toon_bericht("Succes", "Opgeslagen!")

        # Refresh data
        self.refresh()

    except Exception as e:
        # ❌ Fout feedback
        self.toon_fout("Fout", str(e))
```

---

### 5. Bevestiging Pattern

**Destructieve acties bevestigen:**

```python
def _on_verwijderen(self) -> None:
    # Haal geselecteerd item
    item = self._get_geselecteerd_item()

    # Bevestig
    if not self.bevestig_actie(
        "Bevestig Verwijdering",
        f"Weet u zeker dat u '{item.naam}' wilt verwijderen?"
    ):
        return  # Geannuleerd

    # Voer uit
    try:
        Service.verwijder(item.id)
        self.toon_bericht("Succes", "Verwijderd")
        self.refresh()
    except Exception as e:
        self.toon_fout("Fout", str(e))
```

---

### 6. Loading State Pattern

**Toon loading tijdens long-running operations:**

```python
def _laad_data(self) -> None:
    # Disable UI
    self.setEnabled(False)
    self.setCursor(Qt.CursorShape.WaitCursor)

    try:
        # Long operation
        data = Service.haal_grote_dataset()
        self._vul_ui(data)

    finally:
        # Enable UI (always)
        self.setEnabled(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
```

---

### 7. Layout Nesting Pattern

**Nested layouts voor complexe UI:**

```python
def build_ui(self, layout: QVBoxLayout) -> None:
    # Header section
    header_layout = QHBoxLayout()
    header_layout.addWidget(QLabel("Titel"))
    header_layout.addStretch()
    header_layout.addWidget(self.refresh_btn)
    layout.addLayout(header_layout)

    # Content section (2 kolommen)
    content_layout = QHBoxLayout()

    # Linker kolom
    linker_layout = QVBoxLayout()
    linker_layout.addWidget(self.lijst)
    content_layout.addLayout(linker_layout, 2)  # 2/3 breedte

    # Rechter kolom
    rechter_layout = QVBoxLayout()
    rechter_layout.addWidget(self.details_panel)
    content_layout.addLayout(rechter_layout, 1)  # 1/3 breedte

    layout.addLayout(content_layout)
```

---

### 8. QSplitter Pattern (Resizable Panels)

**Resizable side panels:**

```python
from PyQt6.QtWidgets import QSplitter

def build_ui(self, layout: QVBoxLayout) -> None:
    splitter = QSplitter(Qt.Orientation.Horizontal)

    # Main content (70%)
    splitter.addWidget(self.main_widget)

    # Side panel (30%)
    splitter.addWidget(self.side_panel)

    # Set stretch factors
    splitter.setStretchFactor(0, 7)
    splitter.setStretchFactor(1, 3)

    layout.addWidget(splitter)
```

---

## Zie Ook

- [Database Schema Referentie](./database_schema.md) - Database structuur
- [Domein Objecten Referentie](./domein_objecten.md) - Business logic
- [Services API Referentie](./services_api.md) - Service methodes
- [Configuratie Referentie](./configuratie.md) - Systeem configuratie
- [Navigatie Framework Implementatieplan](../plannen/navigatie_framework_implementatie.md) - Gedetailleerde navigatie docs

---

**Einde GUI Components Referentie**
