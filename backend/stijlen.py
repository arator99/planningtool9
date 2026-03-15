"""
Centrale stijlgids voor v0.8 (web).

Dezelfde structuur als v0.7 src/gui/stijlen/kleuren.py,
vertaald naar CSS custom properties voor de browser.

Gebruik: sjablonen.globals['thema'] = thema_css
In templates: var(--primair), var(--grid-verlof), etc.
"""

LIGHT_KLEUREN: dict[str, str] = {
    # Basis
    "primair":              "#2563eb",
    "primair-hover":        "#1d4ed8",
    "secundair":            "#64748b",
    "succes":               "#10b981",
    "waarschuwing":         "#f59e0b",
    "fout":                 "#ef4444",
    "fout-donker":          "#dc2626",
    "info":                 "#3b82f6",
    # Achtergronden
    "achtergrond":          "#f1f5f9",
    "achtergrond-widget":   "#ffffff",
    "achtergrond-alt":      "#f8fafc",
    "achtergrond-accent":   "#f5f5f5",
    # Tekst
    "tekst":                "#0f172a",
    "tekst-secundair":      "#64748b",
    "tekst-donker":         "#212121",
    # Randen & hover
    "rand":                 "#e2e8f0",
    "hover-bg":             "#f1f5f9",
    # Nav
    "nav-bg":               "#ffffff",
    "nav-rand":             "#e2e8f0",
    # Berichten
    "msg-info-bg":          "#dbeafe",
    "msg-succes-bg":        "#d1fae5",
    "msg-waarschuwing-bg":  "#fef3c7",
    "msg-fout-bg":          "#fee2e2",
    # HR-validatie
    "hr-info-bg":           "#e3f2fd",
    "hr-info-rand":         "#1976d2",
    "hr-info-tekst":        "#1976d2",
    "hr-warning-bg":        "#fff3e0",
    "hr-warning-rand":      "#ffb74d",
    "hr-warning-tekst":     "#f57c00",
    "hr-critical-bg":       "#ffebee",
    "hr-critical-rand":     "#ef5350",
    "hr-critical-tekst":    "#d32f2f",
    # Grid celkleuren
    "grid-vroeg":           "#E3F2FD",
    "grid-vroeg-tekst":     "#1565C0",
    "grid-laat":            "#FFF3E0",
    "grid-laat-tekst":      "#E65100",
    "grid-nacht":           "#F3E5F5",
    "grid-nacht-tekst":     "#6A1B9A",
    "grid-dag":             "#ffffff",
    "grid-dag-tekst":       "#424242",
    "grid-rust":            "#E8F5E9",
    "grid-rust-tekst":      "#2E7D32",
    "grid-standby":         "#FAFAFA",
    "grid-standby-tekst":   "#616161",
    "grid-ziekte":          "#FFEBEE",
    "grid-ziekte-tekst":    "#C62828",
    "grid-weekend":         "#f0f4ff",
    "grid-weekend-tekst":   "#3b82f6",
    "grid-header":          "#f8fafc",
}

DARK_KLEUREN: dict[str, str] = {
    # Basis
    "primair":              "#3b82f6",
    "primair-hover":        "#2563eb",
    "secundair":            "#64748b",
    "succes":               "#10b981",
    "waarschuwing":         "#f59e0b",
    "fout":                 "#ef4444",
    "fout-donker":          "#f87171",
    "info":                 "#60a5fa",
    # Achtergronden
    "achtergrond":          "#0f172a",
    "achtergrond-widget":   "#1e293b",
    "achtergrond-alt":      "#1e293b",
    "achtergrond-accent":   "#2d3748",
    # Tekst
    "tekst":                "#f1f5f9",
    "tekst-secundair":      "#94a3b8",
    "tekst-donker":         "#212121",
    # Randen & hover
    "rand":                 "#334155",
    "hover-bg":             "#334155",
    # Nav
    "nav-bg":               "#1e293b",
    "nav-rand":             "#334155",
    # Berichten
    "msg-info-bg":          "#1e3a8a",
    "msg-succes-bg":        "#064e3b",
    "msg-waarschuwing-bg":  "#78350f",
    "msg-fout-bg":          "#7f1d1d",
    # HR-validatie
    "hr-info-bg":           "#1e3a5f",
    "hr-info-rand":         "#60a5fa",
    "hr-info-tekst":        "#93c5fd",
    "hr-warning-bg":        "#78350f",
    "hr-warning-rand":      "#fbbf24",
    "hr-warning-tekst":     "#fcd34d",
    "hr-critical-bg":       "#7f1d1d",
    "hr-critical-rand":     "#f87171",
    "hr-critical-tekst":    "#fca5a5",
    # Grid celkleuren (donkere varianten)
    "grid-vroeg":           "#1e3a5f",
    "grid-vroeg-tekst":     "#93c5fd",
    "grid-laat":            "#78350f",
    "grid-laat-tekst":      "#fcd34d",
    "grid-nacht":           "#4c1d95",
    "grid-nacht-tekst":     "#c4b5fd",
    "grid-dag":             "#1e293b",
    "grid-dag-tekst":       "#cbd5e1",
    "grid-rust":            "#064e3b",
    "grid-rust-tekst":      "#6ee7b7",
    "grid-standby":         "#374151",
    "grid-standby-tekst":   "#9ca3af",
    "grid-ziekte":          "#7f1d1d",
    "grid-ziekte-tekst":    "#fca5a5",
    "grid-weekend":         "#1e2d4f",
    "grid-weekend-tekst":   "#60a5fa",
    "grid-header":          "#1e293b",
}


def maak_css_variabelen(kleuren: dict[str, str]) -> str:
    """Genereer CSS custom properties string vanuit een kleurendict."""
    regels = ["  " + f"--{k}: {v};" for k, v in kleuren.items()]
    return ":root {\n" + "\n".join(regels) + "\n}"


def maak_dark_override(kleuren: dict[str, str]) -> str:
    """Genereer CSS custom properties string voor dark mode override."""
    regels = ["  " + f"--{k}: {v};" for k, v in kleuren.items()]
    return "[data-theme='dark'] {\n" + "\n".join(regels) + "\n}"


def genereer_thema_css() -> str:
    """Genereer volledige thema CSS met light en dark mode."""
    return (
        maak_css_variabelen(LIGHT_KLEUREN)
        + "\n\n"
        + maak_dark_override(DARK_KLEUREN)
    )
