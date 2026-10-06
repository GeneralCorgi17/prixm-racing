# UI Themes — ◐ Nothing (default) + Classic

`daily_racing_analyzer.html` has two looks. Switch any time with the **◐** button in the header. The choice is saved per browser in `localStorage.uiTheme`.

| Theme | `uiTheme` | Since | Look |
|-------|-----------|-------|------|
| **◐ Nothing** (default) | `'nothing'` (or unset) | 2026-10-02 | Dark, in the style of getnothing.club |
| **Classic** ("Editorial White") | `'classic'` | 2026-06-29/30 | Light warm-white editorial (previous default) |

Both run off the same code. Nothing changes data, scores, segments, picks or P&L.

---

## How it's built

1. **Head script** runs before any CSS, right after `<title>`. It reads `localStorage.uiTheme` (inside try/catch) and sets `<html data-theme="nothing|classic">`. Anything other than `'classic'` gives Nothing.
2. **Fonts**: a Google Fonts `<link>` loads Bebas Neue, DM Mono and Quantico. They are only used under `data-theme="nothing"`.
3. **`<style id="themeNothing">`** sits right after the main `</style>`. Every rule is scoped to `html[data-theme="nothing"]`, so the Classic CSS (lines ~7–1148) is **untouched**.
   - It overrides the `:root` vars: `--bg #0a0a0a`, `--card #0a0a0a`, `--card2 #141414`, `--text #f5f2eb`, `--muted #8a857c`, `--border #222`, `--accent #c8b89a` (sand), `--gold #d9b25c`, `--em #5bb39a`.
   - It sets component styles: header (PRIXM in Bebas + outlined Quantico "ANALYZER"), sticky tab bar with a sand underline, hairline stats strip, underline venue chips, square filter pills, hairline race-card grid (Bebas time/pick/stats, Golden/Silver/Bronze 2px top line), sidebar panels, race detail (Bebas title, hairline runner table, sand inset on the top pick), modals, the Ledger FAB as a brutalist button, the splash screen, and dark turf on the race-track SVGs (MT / Predict).
   - A Classic-only rule pins the ◐ button at the header's top-right (out of flow), so the Classic layout is pixel-identical to before.
4. **`NOTHING THEME JS` block** sits at the very end of the file, before `</body>`.
   - `toggleTheme()` switches the saved theme and reloads the page. Reloading means nothing has to be undone at runtime.
   - `ntRemap(root)` exists because the Classic UI has ~400 inline styles and many hard-coded light CSS colours that the var override can't reach. It reads **computed** colours and:
     - turns light backgrounds dark, keeping the hue (neutral → `#0a0a0a` / `#141414`, tinted → 10–14% lightness tint);
     - removes light gradients;
     - lightens dark text, keeping the hue (neutral → cream / grey, coloured → 72% lightness);
     - darkens light borders.
     It writes inline `!important` values and remembers the originals in a `WeakMap`.
   - A `MutationObserver` re-sweeps added nodes once per animation frame. When a `class` attribute changes, it restores the originals and re-sweeps.
   - Hover states that turn light are darkened while hovered and restored on mouseleave.
   - The custom cursor (dot + lagging ring, `mix-blend-mode:difference`) is added only for a mouse (`pointer:fine`).
5. **One theme-aware line in app code**: `renderRaceCards()` colours the score number and top-pick bar by tier. Nothing uses green `#9fd6ae` / cream / grey, Classic keeps `#059669` / `#1d4ed8` / `#9ca3af`.

**Out of scope (stay light on purpose):** the PDF/print export documents (they open as their own documents with their own `<style>`), plus canvas-drawn charts if any are added later.

**Reference:** (the mockup files were removed 2026-10-06 once the theme was live)
- Source site: https://getnothing.club (palette `#0a0a0a / #f5f2eb / #1a1a1a / #3a3a3a / #c8b89a`, grain overlay, custom cursor, fadeUp/reveal, 1px-gap hairline grids, brutalist button hover).

---

## Classic theme (Editorial White), kept for reverting

The Classic theme is the main stylesheet exactly as it was at commit `f7e4ed2`. Git tag **`ui-classic-2026-10-02`** points at it.

- **Root vars:** `--bg:#f0ede8; --card:#fff; --card2:#f5f3f0; --accent:#15803d; --accent2:#3b82f6; --warn:#d97706; --danger:#ef4444; --text:#111827; --muted:#6b7280; --border:#e5e0d8; --gold:#d97706`
- **Font:** `'Segoe UI', system-ui, sans-serif`.
- **Contrast rules (light bg):** minimum 4.5:1. Forest green `#15803d`, dark amber `#b45309`, blue `#1d4ed8`, purple `#7c3aed`, red `#dc2626`.
- **Factor bars:** `#5D4A66` strong / `#C1CEFE` good / `#B2BD7E` marginal / `#EC7357` poor.
- **Race cards:** 3-column white box cards with a 5px left border (blue ENG NH / amber ENG HCP / green IRE NH / red IRE HCP). Golden cards have an amber tint, Silver a blue tint.
- **Dark overlays kept dark** in Classic: `.hcmp-*`, `.hs-*`, `.bet-type-popup`, `.bet-panel`.

## How to revert

| Want | Do |
|------|----|
| Classic for me, now | Click **◐ Classic** in the header (or `localStorage.setItem('uiTheme','classic')` and reload) |
| Classic as the default for everyone | In the head script change `||'nothing'` → `||'classic'` (and the fallback `'nothing'` → `'classic'`) |
| Remove Nothing completely | Delete the `<style id="themeNothing">` block, the `NOTHING THEME JS` `<script>`, the head script + fonts `<link>`, the `◐` button (`.nt-toggle`), and restore the one `const col=` line in `renderRaceCards()` |
| Exact old file | `git checkout ui-classic-2026-10-02 -- daily_racing_analyzer.html` (loses any later changes to that file) |

## Phone layout

Separate from the themes: `<style id="phoneLayout">` (≤700px) restyles the layout for phones in **both** themes (bottom nav, ☰ sheet, picks strip, stacked runner cards). See CLAUDE.md → 📱 Phone layout. `ntRemap()` keeps the theme palette (cream/sand/green/blue/gold/silver/red/emerald/amber) and dark text on cream surfaces untouched (`KEEP`, `onKeptBg`).

## Extending the Nothing theme

- New components: add rules under `html[data-theme="nothing"]` in `#themeNothing`. Prefer the vars.
- Anything light that gets past is caught by `ntRemap()`. If something must keep a light colour (e.g. a jockey silk), it is an `<img>`/`<svg>`, which the remap skips.
- New SVGs with hard-coded light fills: override them by attribute, e.g. `html[data-theme="nothing"] svg [fill="#cfe6d3"]{fill:#15241b}` (CSS beats SVG presentation attributes).
