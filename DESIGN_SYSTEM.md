# Design System — TradingAgents Web Console

> Governs `webui/static/`. The console is a single-page, dependency-free frontend; every token below is a CSS custom property in `app.css`.

## Design principles

1. **Trading-desk calm.** Dark, low-glare surfaces; color is reserved for *signal* (decisions, status, errors) — never decoration. If everything glows, nothing does.
2. **Numbers are first-class.** Anything tabular or identifier-like (tickers, dates, run IDs, log output) renders in the mono stack with tabular numerals so columns align.
3. **Content over chrome.** Reports are the product; the shell stays in the background (one masthead, no sidebars stealing width from 75ch reading columns).
4. **Honest states.** Every async surface has explicit loading, empty, error, and success treatments. An empty state always says what would fill it and links there.
5. **Zero supply chain.** No fonts, frameworks, icons, or CDNs. The entire UI ships as three static files served same-origin under a `default-src 'self'` CSP.

## Color system

| Token | Value | Role |
|---|---|---|
| `--bg` | `#0d1117` | App background |
| `--bg-raise` | `#161b22` | Cards, masthead |
| `--bg-inset` | `#0a0e13` | Code/log wells, inputs |
| `--line` | `#2d333b` | Hairline borders |
| `--text` | `#e6edf3` | Primary text — **16.0:1** on `--bg` |
| `--text-dim` | `#9aa7b1` | Secondary text — **7.7:1** on `--bg` |
| `--accent` / `--buy` | `#3fd68f` | Primary actions, BUY, success — 10.1:1 on `--bg` |
| `--sell` | `#ff7b72` | SELL, failures — 6.9:1 on `--bg-raise` |
| `--hold` | `#d29922` | HOLD, caution — 6.9:1 on `--bg-raise` |
| `--info` | `#58a6ff` | Links, running state — 6.8:1 on `--bg-raise` |

Contrast ratios are computed (WCAG relative luminance), not estimated; every text pair meets AA (≥4.5:1) and most meet AAA (≥7:1). Decision semantics are never conveyed by color alone — badges always carry the word (BUY/SELL/HOLD).

## Typography

- **UI stack:** `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` — native rendering, zero font downloads.
- **Mono stack:** `ui-monospace, "SF Mono", "Cascadia Code", Menlo, Consolas, monospace` with `font-variant-numeric: tabular-nums`.
- Base 15px/1.55. Scale: h2 22px, h3 16px, body 15px, table/report detail 13.5–14px, badges/log 11.5–12px mono.
- Report prose constrained to `75ch` for readability.

## Layout system

- **4px base grid**: spacing tokens `--s1`(4) `--s2`(8) `--s3`(12) `--s4`(16) `--s6`(24) `--s8`(32). No off-grid spacing.
- Content column `max-width: 1100px`, centered; sticky masthead; footer disclaimer.
- Card grid: `repeat(auto-fill, minmax(290px, 1fr))`.
- **Responsive:** single breakpoint at 760px — nav wraps, grids collapse to one column, optional table columns (`.opt`) hide, connection chip hides. Layout is fluid between breakpoints, not stepped.

## Components

| Component | Class | Notes |
|---|---|---|
| Card | `.card` | Raised surface, 1px hairline, 8px radius |
| Badge | `.badge` + `-buy/-sell/-hold/-running/-failed/-completed` | Pill, mono uppercase; word + color |
| Banner | `.banner` + `-error/-ok` | `role="alert"` on errors |
| Empty state | `.empty` | Dashed border; explains + links the filling action |
| Loading | `.loading` + `.spinner` | Animated ring; slows under `prefers-reduced-motion` |
| Data table | `table.list` | Uppercase dim headers, hairline rows |
| Report | `.report` | Rendered-markdown container (escaped first) |
| Collapsible section | `details.section` | Native `<details>` — keyboard/screen-reader free |
| Log well | `.log-well` | Inset mono, pre-wrap, scrollable, focusable (`tabindex="0"`) |
| Key/value | `dl.kv` | Two-column definition grid |
| Buttons | `.btn`, `.btn-primary`, `.btn-link` | Primary = accent fill; disabled at .5 opacity |
| Form field | `.field` | Label above input, `.hint` below |

## Interaction patterns

- **Navigation:** hash routing (`#/dashboard`, `#/results`, `#/results/<t>/<d>`, `#/new`, `#/runs/<id>`, `#/memory`, `#/settings`). Active item marked with `aria-current="page"`. Back/forward work natively.
- **Keyboard:** skip-link to `#main`; all interactive elements are native `<a>/<button>/<input>/<details>`; visible `:focus-visible` outline (2px `--info`).
- **Live data:** active runs poll every 2.5s, only while a non-terminal run is on screen; a 15s heartbeat drives the connection chip (`aria-live="polite"`).
- **Destructive/costly actions:** launching an analysis states cost and duration up front; the submit button disables and re-labels while in flight; failures return focusable error banners with the server's actionable message.
- **Exports:** report download is a plain `<a download>` to the markdown export endpoint — no JS blob machinery.

## Accessibility checklist (validated)

- Semantic landmarks: `header/nav/main/footer`, one `h1`, ordered headings.
- Skip link, labeled form controls, `aria-live` regions for async content, `role="alert"` on errors.
- Measured AA+ contrast (table above); information never color-only.
- `prefers-reduced-motion` respected; no autoplaying or flashing content.
- Known gap: not yet audited with a real screen reader or automated axe pass (no browser in the validation environment) — see FINAL_PRODUCTION_READINESS_ASSESSMENT.md.
