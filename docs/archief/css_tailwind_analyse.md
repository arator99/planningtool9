# CSS / Tailwind Analyse — Planningtool v0.9
**Datum:** 2026-03-16
**Status:** Bevindingen na debug-sessie (meerdere uren)

---

## Kernprobleem: Twee onafhankelijke CSS-systemen

De applicatie heeft **twee layouts die elk hun eigen, compleet andere CSS-aanpak** gebruiken:

| | `templates/base.html` | `templates/layouts/app.html` |
|---|---|---|
| **Gebruikt door** | Loginpagina | Alle authenticated pagina's |
| **CSS variabelen** | `theme.css` via `<link>` | `stijlen.py` → `{{ thema_css \| safe }}` |
| **Variabelenamen** | `--kleur-primair` (RGB kanalen) | `--primair` (hex) |
| **Tailwind dark mode** | `darkMode: 'class'` → `html.dark` | `darkMode: ['attribute', 'data-theme']` → `data-theme="dark"` |
| **Kleur in Tailwind config** | Hardcoded hex `#2563eb` | CSS var `var(--primair)` |

Deze twee systemen zijn **niet compatibel** met elkaar.

---

## Oorzaak van onzichtbare knoppen

### Wat werkt WEL

```html
<!-- 1. Inline style — altijd zichtbaar, onafhankelijk van CSS-cascade -->
<button style="background-color: var(--primair); color: #fff;">

<!-- 2. Standaard Tailwind utility classes -->
<button class="px-4 py-2 rounded-lg border">

<!-- 3. Native Tailwind kleuren -->
<button class="bg-blue-600 text-white">
```

### Wat werkt NIET (in app.html pagina's)

```html
<!-- bg-primair via Tailwind CDN — onzeker gedrag -->
<button class="bg-primair text-white">
```

**Waarom?** Tailwind Play CDN genereert CSS voor `bg-primair` als:
```css
.bg-primair { background-color: var(--primair); }
```
Dit hangt af van of Tailwind CDN de klasse überhaupt verwerkt. Als de CDN een JS-fout heeft (door backslash-selectors elders in de pagina), stopt het verwerken van alle klassen.

### De backslash-selector SyntaxError

In eerdere versies stond in `base.html` (en `theme.css`) code zoals:
```css
.hover\:bg-primair-hover:hover { ... }
```
De backslash-escaped selector **veroorzaakte een `Uncaught SyntaxError`** in de Tailwind Play CDN JavaScript parser. Dit brak Tailwind's volledige CSS-generatie voor de pagina.

**Gevolg:** Alle `bg-*`, `text-*`, `border-*` klassen worden **niet** gegenereerd → witte tekst op witte achtergrond.

---

## CSS Cascade Volgorde (app.html pagina's)

```
1. Tailwind config (lines 7-27 van app.html)
   → tailwind = { config: { colors: { primair: 'var(--primair)' } } }

2. Tailwind CDN script geladen + config ingelezen

3. <style>{{ thema_css | safe }}</style>  (lijn 31)
   → :root { --primair: #2563eb; ... }
   → [data-theme='dark'] { --primair: #3b82f6; ... }

4. <style>body { background: var(--achtergrond); }</style>  (lijn 32-35)

5. DOMContentLoaded → Tailwind scant DOM → genereert <style> tag
   → .bg-primair { background-color: var(--primair); }
   → De gegenereerde <style> staat NA stap 3/4 in cascade
```

Zonder `!important`: Tailwind wint (maar dat is OK, want var(--primair) is correct).

---

## CSS Cascade Volgorde (base.html pagina's — login)

```
1. Tailwind config (met hex kleuren)
2. Tailwind CDN
3. theme.css via <link> → .bg-primair { background-color: #2563eb !important; }
   (maar base.html wordt ENKEL gebruikt voor de loginpagina)
```

`theme.css` heeft geen invloed op `app.html` pagina's want het wordt daar niet geladen.

---

## Dark Mode Inconsistentie

| Mechansime | Waar actief | Script |
|---|---|---|
| `html.dark` class | `base.html` (login) | `document.documentElement.classList.add('dark')` |
| `[data-theme='dark']` attr | `app.html` (alle andere) | `HTML.setAttribute('data-theme', 'dark')` |

Als een gebruiker dark mode instelt via de navbar-toggle (op een app.html pagina), en dan naar de loginpagina navigeert, werkt dark mode niet op de loginpagina — en omgekeerd.

---

## Concrete Bevindingen per Element

| Element | Bestand | Klasse | Zichtbaar? | Reden |
|---|---|---|---|---|
| Login knop | `login.html` / `base.html` | `bg-primair text-white` | ✅ | Tailwind config met hex → genereert correct |
| Nieuwe gebruiker knop | `gebruikers/lijst.html` / `app.html` | `bg-primair text-white` | ❌ | Afhankelijk van Tailwind CDN generatie |
| Aanmaken knop | `gebruikers/formulier.html` / `app.html` | `bg-primair text-white` | ❌ | Zelfde probleem |
| Nav links | `app.html` | `style="color: var(--tekst)"` | ✅ | Inline style, altijd zichtbaar |
| Dropdown hover | `app.html` | `onmouseover="style.background=..."` | ✅ | JavaScript, altijd zichtbaar |
| Uitloggen knop | `app.html` | `style="color: var(--fout)"` | ✅ | Inline style |

---

## Waarom `bg-primair` soms WEL werkt

Als er geen JS SyntaxError is en Tailwind CDN correct draait:
- Tailwind genereert `.bg-primair { background-color: var(--primair); }`
- `--primair: #2563eb` is gedefinieerd in `thema_css`
- Resultaat: blauwe knop ✓

Maar dit is **fragiel**: bij elke Tailwind CDN parser-fout elders op de pagina valt alles weg.

---

## Aanbevelingen

### Optie A — Vertrouw volledig op CSS variabelen (huidige app.html aanpak)

Vervang in alle templates `bg-primair` door `style="background-color: var(--primair)"` etc.
**Pro:** Werkt altijd, onafhankelijk van Tailwind. **Con:** Meer verbose HTML.

### Optie B — Verwijder Tailwind CDN, gebruik alleen CSS variabelen

`app.html` bevat al een compleet CSS-variabelensysteem via `stijlen.py`.
Gebruik Tailwind **alleen voor layout/spacing** (padding, margin, flexbox, grid).
Gebruik **nooit** `bg-*`, `text-*`, `border-*` met semantische kleuren via Tailwind.
**Pro:** Eén systeem, geen CDN-conflicten. **Con:** Semantische kleurklassen via Tailwind niet meer beschikbaar.

### Optie C — Twee systemen samenvoegen

Vervang `base.html` én `app.html` door één uniforme layout.
Kies **één dark mode mechanisme** (`html.dark` OF `data-theme`).
Kies **één kleurensysteem** (CSS variabelen OF Tailwind config).
**Pro:** Consistent. **Con:** Grote refactor van alle templates.

### Optie D — Tailwind `safelist` + PostCSS build (geen CDN)

Bouw Tailwind offline, genereer een statisch CSS-bestand.
**Pro:** Geen runtime CDN-gedoe, volledige JIT. **Con:** Vereist build-stap in Docker.

---

## Huidige Workaround (actief)

De "Nieuwe gebruiker" knop in `gebruikers/lijst.html` gebruikt:
```html
style="background-color: var(--primair); color: #fff;"
```
Dit werkt altijd omdat `--primair` gedefinieerd is in `thema_css`.
Alle knoppen die onzichtbaar zijn kunnen op dezelfde manier gefixed worden als tijdelijke maatregel.

---

## Conclusie

Het kernprobleem is **architecturaal**: twee layouts met twee CSS-systemen die elk half werken.
De fragielheid zit in het afhankelijk zijn van Tailwind Play CDN voor semantische kleuren,
terwijl er al een volledig werkend CSS-variabelensysteem aanwezig is in `stijlen.py`.

**Aanbeveling:** Kies één aanpak en pas alle templates consistent aan.
