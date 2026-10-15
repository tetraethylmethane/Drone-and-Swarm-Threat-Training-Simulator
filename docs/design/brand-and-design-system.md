# Brand and design system

## Brand assets

The Drikr Systems logo and mark are the official artwork supplied with the Drikr NIDAR ground-station
project (`Drikr-NIDAR/ground-station/frontend/public/drikr-logo.png` and `drikr-mark.png`). The
originals are kept unchanged in `assets/brand/source/`:

| Original | SHA-256 |
|---|---|
| `drikr-logo.png` | `60092b94…3495` |
| `drikr-mark.png` | `944d3b0e…5c36` |

Derived files in `assets/brand/` were made only by cropping to the artwork, making the background
transparent and resizing. Colours and letterforms are unchanged.

| File | Use |
|---|---|
| `drikr-logo.png` (1236 × 222, ink `#1B1F1D`) | Web app header and sign-in page, PDF reports, Unity client header |
| `drikr-logo-light.png`, `drikr-mark-light.png` | Light versions for dark backgrounds (not used by the current light interface) |
| `drikr-mark-{16,32,48,64,180,256}.png`, `drikr-mark.ico` | Favicon, touch icon, Unity application icon |

The NIDAR ground station's dark, monospace dashboard is a different product, and its interface
style is **not** adopted here. Only the logo and mark are shared. The interface colours below are
this product's own design tokens (forest green as specified in the brief); they are not taken from
official brand guidelines, which were not supplied.

## Where assets are used

| Asset | Location |
|---|---|
| Logo in the web app | `apps/web/public/brand/` rendered by `apps/web/src/components/layout/Wordmark.tsx` |
| Favicon and touch icon | `apps/web/public/favicon.ico`, `apps/web/public/brand/drikr-mark-{32,180}.png` (linked from `index.html`) |
| PDF reports | `apps/api/drikr_api/assets/drikr-logo.png`, drawn by `services/report_service.py` |
| Unity client | `Assets/Drikr/Resources/DrikrBrand/drikr-logo.png` (header); `Assets/Drikr/Brand/drikr-mark-256.png` (application icon, set by `BuildScript`) |
| Colour tokens | `apps/web/src/styles.css`: `:root` variables, exposed to Tailwind 4 through the `@theme` block |
| Typeface | `@fontsource/inter` imports and `--font-sans` in `styles.css` |
| Chart palette | `CHART_COLORS` in `apps/web/src/components/charts/EChart.tsx` |
| PDF report colours | `FOREST`, `RULE`, `MUTED` in `apps/api/drikr_api/services/report_service.py` |

## Tokens

| Token | Value | Use |
|---|---|---|
| canvas | `#F6F5F1` | Page background (warm off-white) |
| surface / surface-muted | `#FFFFFF` / `#EFEEE9` | Panels / table headers, skeletons |
| border / border-strong | `#DCD9D1` / `#C6C2B8` | Dividers / inputs |
| ink / ink-muted / ink-subtle | `#1B1F1D` / `#545A56` / `#636864` | Text (all ≥ 4.5:1 on canvas; `ink-subtle` darkened after an axe contrast failure) |
| brand / brand-hover / brand-soft | `#1F4D3A` / `#183D2E` / `#E3ECE6` | Primary actions, active navigation, focus ring |
| success / warning / danger / info | `#28623F` / `#85560E` / `#9B2C2C` / `#2D4F73` with soft backgrounds | Small status tags and alerts |

Radii: 4 px (controls), 6 px (panels). Shadow: 1 px hairline only. Type: Inter 400/500/600,
14 px base, tabular numerals in tables and clocks.

## Rules

* No monospace in the product interface (enforced by an ESLint rule on `font-mono` and an E2E check).
* No gradients, glow, glass effects, decorative grids, illustrations, emoji or decorative arrows.
* Icons only where they carry function; status is always text, never colour alone.
* Information first: tables, numbered sections and labels rather than diagrams.
* Every interactive element has a visible focus ring; a skip link precedes navigation.
* Track colours in the exercise views follow the **trainee's own classification**, never ground truth.

Reference screenshots of key screens: `docs/design/screens/`.
