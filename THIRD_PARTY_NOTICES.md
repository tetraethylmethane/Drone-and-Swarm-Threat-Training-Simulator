# Third-party notices

Licence data was collected on 2026-10-14 from installed package metadata (`importlib.metadata`
for Python; `package.json` of every production dependency resolved by `npm ls --omit=dev --all`).
No source code from the research references in `docs/research-review.md` is included. The
repositories and papers were re-verified on 2026-10-16 (`docs/research/research-and-reuse.md`).
Again no code, models or assets were reused, so they need no attribution here. Brand artwork:
official Drikr Systems logo and mark (`assets/brand/source/`), used by the owner's direction. No 3D models,
textures, terrain data or external datasets are bundled: all scenes are generated geometrically and
all scenario data is original synthetic content.

## Licences requiring attention

| Component | Licence | Obligation / note |
|---|---|---|
| Inter typeface (`@fontsource/inter` 5.1.0) | SIL Open Font License 1.1 | Font files are bundled into the web build. The OFL permits bundling and redistribution; the font must not be sold by itself, and the licence text must accompany redistributed font files (included in the package at `node_modules/@fontsource/inter/LICENSE`). |
| psycopg, psycopg-binary 3.2.3 | LGPL-3.0 | Used unmodified as a dynamically imported library. Distributing the API image therefore includes LGPL components: provide the licence text and allow replacement of the library (satisfied by standard pip installation). |
| certifi | MPL-2.0 | Unmodified. Source available from PyPI. |
| echarts 6.1.0, class-variance-authority | Apache-2.0 | Keep the licence and NOTICE files when redistributing. |
| PostgreSQL 17 (container image) | PostgreSQL Licence | Permissive. |
| nginx (nginxinc/nginx-unprivileged image) | BSD-2-Clause | Permissive. |

## Unity client (`apps/simulator/DrikrUnityClient`)

| Component | Licence | Note |
|---|---|---|
| Unity Engine runtime 6000.3.26f1 (player binaries in the Windows build) | Unity Terms of Service / Unity Editor Software Terms | Redistribution of built players is governed by the licence tier of the account that builds it. Unity Personal builds show the Unity splash screen. Confirm the tier before distributing. |
| Newtonsoft.Json (`com.unity.nuget.newtonsoft-json` 3.2.1) | MIT | Bundled in the player |
| Unity Test Framework 1.6.0 / NUnit | Unity Companion Licence / MIT | Editor and tests only, not in the player |

| Sky images (HDRI): *Kloofendal 48d Partly Cloudy (Pure Sky)*, *Kloppenheim 06 (Pure Sky)*, *Overcast Soil (Pure Sky)*, *Moonless Golf*, from [Poly Haven](https://polyhaven.com/) | CC0 1.0 (public domain) | `Assets/Drikr/Resources/DrikrEnv/sky_*.hdr`, downloaded 2026-10-19 through the Poly Haven API. No attribution required; credited here as a courtesy |
| Ground textures: Grass001, Concrete034, Ground054, Ground037 from [ambientCG](https://ambientcg.com/) | CC0 1.0 (public domain) | `Assets/Drikr/Resources/DrikrEnv/ground_*` (1K colour and normal maps), downloaded 2026-10-19 |

The 3D models (drones, fixed-wing aircraft, birds, buildings, trees, radar) are built in code from
engine primitives (`ContactModels.cs`, `Scenery.cs`); no third-party models or audio are used.

## Production web dependencies (shipped in the browser bundle)

* **MIT (65 packages):** react, react-dom, react-router, react-router-dom, @react-three/fiber, three,
  zod, clsx, tailwind-merge, all `@radix-ui/*` primitives used, zustand, scheduler,
  react-reconciler, its-fine, suspend-react, aria-hidden, react-remove-scroll and its helpers,
  @babel/runtime, cookie, set-cookie-parser, debounce, buffer, base64-js and type-only packages.
* **Apache-2.0:** echarts, class-variance-authority.
* **BSD-3-Clause:** zrender, ieee754.
* **0BSD:** tslib.
* **OFL-1.1:** @fontsource/inter.

Exact versions: `apps/web/package-lock.json`.

## Python runtime dependencies (API image)

| Licence | Packages |
|---|---|
| MIT | fastapi, pydantic, pydantic-core, pydantic-settings, sqlalchemy, alembic, mako, argon2-cffi, argon2-cffi-bindings, anyio, h11, httptools, watchfiles, pyyaml, typing-inspection, annotated-types, annotated-doc, greenlet (MIT and PSF-2.0), cffi (MIT-0) |
| BSD | starlette, uvicorn, websockets, click, python-dotenv, idna, markupsafe, pycparser, reportlab, segno (QR codes for MFA enrolment) |
| Apache-2.0 OR BSD-3-Clause | cryptography (AES-GCM sealing of MFA secrets) |
| Apache-2.0 | opentelemetry-api (pulled in by FastAPI; API only, no SDK or exporter, so no data is collected or sent — enforced by `tests/unit/test_offline.py`), tzdata |
| LGPL-3.0 | psycopg, psycopg-binary |
| PSF-2.0 | typing-extensions |

## Development and test tools (not distributed)

pytest, pytest-cov, coverage, httpx, ruff, mypy, pip-audit (and dependencies), Vite, Vitest,
TypeScript, ESLint, typescript-eslint, eslint-plugin-jsx-a11y, eslint-plugin-react-hooks, Prettier,
Tailwind CSS (@tailwindcss/vite), Testing Library, jsdom, Playwright, @axe-core/playwright.
These are MIT, Apache-2.0, BSD or MPL-2.0 (axe-core) licensed; they are used only to build and test.

## Licence texts

Full licence texts are distributed inside each package (`site-packages/*.dist-info/` for Python;
`node_modules/<package>/LICENSE` for npm). Before redistributing container images, generate a
complete notice bundle (for example with `pip-licenses --with-license-file` and
`license-checker --production`) and include it with the release.
