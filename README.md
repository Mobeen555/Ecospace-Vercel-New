# EcoScope AI · Earth, understood.

**Version 3.0.0 · Vercel edition**  
An environmental research workspace for Mobeen Jamshed Khattak.

A new React interface over the working Python science engine, with exactly five CrewAI agents using Groq. The previous photographs, image frames and icon assets are excluded. Original SVG/CSS illustrations, self-hosted typography and a charcoal / ivory / lime palette provide the new visual identity. EOS inspired the environmental storytelling; its assets and branding are not copied.

**Start with [DEPLOYMENT.md](DEPLOYMENT.md). Upload the entire extracted project, including `backend/`, `api/`, `web/` and `supabase/`. This is not a single-file Streamlit application.**

## What is included

| Workspace | What it does |
|---|---|
| Overview | Original responsive landing page and recent studies |
| Atlas | Interactive Leaflet map, coordinates/place search, polygon drawing, GeoJSON boundaries, georeferenced Sentinel-2 overlays and observation bubbles |
| Analysis | Seven evidence modules, ECharts figures, source tables, quality notes and field-measurement uploads |
| AI studio | Visible five-agent CrewAI workflow, Groq connection, saved progress, citations, specialist notes and final interpretation |
| Reports | PDF, standalone HTML, Excel and complete ZIP; CSV, GeoJSON and available GeoTIFF exports |

Modules: historical climate and current weather forecast; air quality; Sentinel-2 vegetation/water screening; river-discharge outlook; earthquake catalogue; GBIF biodiversity records; official US weather alerts. Citizen measurements can be added after retrieval.

Provider failures are shown. There are no fallback demonstration measurements in the deployed app. Forecasts retain their actual forecast dates rather than adopting the selected historical period. Water indices are screening proxies. This application does not predict earthquakes or provide validated flood/tornado warnings. See [METHODS.md](METHODS.md).

## Deployment architecture

- **Frontend:** React 19, Vite 8, HTML, CSS, JavaScript, Leaflet and ECharts.
- **Backend:** Python **3.12**, FastAPI, Rasterio, pandas and the migrated environmental engine.
- **AI:** CrewAI **1.15.22** and Groq; default `openai/gpt-oss-120b`, configurable on the server.
- **Hosting:** Vercel frontend plus one Python ASGI function. The scientific/CrewAI dependency bundle requires **Vercel Large Functions (public beta) with Fluid compute**.
- **Persistence:** Supabase Postgres metadata and private Storage snapshots/exports. SQLite is available for local development only.
- **Access:** private workspace password and signed browser-session cookie. This version is intended for a controlled research deployment, not enterprise user-account management.

Exactly five agent files live in `backend/agents/`: `coordinator.py`, `climate_air.py`, `geospatial_water.py`, `ecology_field.py`, `reviewer_reporter.py`. Each role executes in a bounded, saved stage. No implicit manager agent is added. CrewAI runs in your Python function; a separate CrewAI hosting subscription is not required.

## Important files

| Path | Purpose |
|---|---|
| `web/src/App.jsx` | All five UI workspaces and study workflow |
| `web/src/styles.css` | Responsive visual system |
| `web/src/visuals.jsx` | Globe illustration, interactive maps and charts |
| `api/index.py` | Vercel ASGI entrypoint |
| `backend/api.py` | Validated, authenticated API routes |
| `backend/environment.py` | Scientific data adapters, calculations and report rendering |
| `backend/analysis.py` | One provider/scene per saved step |
| `backend/review.py` | Exactly five persisted CrewAI stages |
| `backend/evidence.py` | Scoped evidence tools, quality checks and review fingerprint |
| `backend/storage.py` | Supabase / local persistence and update leases |
| `supabase/setup.sql` | Private tables, storage bucket and lease functions |
| `requirements.txt`, `pyproject.toml` | Matching pinned direct Python dependencies |
| `package.json`, `package-lock.json` | Frontend dependency versions |
| `vercel.json` | Vite build, Python function, API routing and headers |
| `.env.example` | Server configuration template, with placeholders only |

## Local development

Install Python 3.12 and Node.js 24. In the project root:

```bash
python -m venv .venv
```

Activate it on Windows PowerShell with `.venv\Scripts\Activate.ps1`, or macOS/Linux with `source .venv/bin/activate`.

```bash
python -m pip install -r requirements.txt
npm ci
```

Copy `.env.example` to `.env`. Set `ECOSCOPE_LOCAL=1`, replace the workspace password and session secret, and either add a real Groq key or leave `GROQ_API_KEY` empty. The local mode does not need Supabase.

Start two terminals in the project root:

```bash
python -m uvicorn api.index:app --reload --port 8000
```

```bash
npm run dev
```

Open **http://localhost:5173**. Vite forwards `/api` requests to Python. Do not open `web/index.html` by double-clicking it. For a compiled local app, run `npm run build` and start the Python server; it then serves the built interface at http://localhost:8000.

## Verification

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
npm test
npm run build
```

Tests use clearly labelled synthetic fixtures and controlled model responses. They never become deployed study results. Actual verification evidence and remaining cloud checks are recorded in [VALIDATION.md](VALIDATION.md).

## Data retention and access

Saved studies belong to this browser session, which lasts 30 days. Clearing cookies, changing the signing secret or using another browser will not restore the earlier workspace. This release has no email login, cross-device sharing or account recovery. Download the report/data ZIP for durable, portable research records. Server administrators can manage stored data directly in Supabase.

Open-source code does not mean unlimited free hosting, storage, AI calls or data API usage. Review the provider terms and account quotas linked in the deployment guide before broad public or commercial use.

MIT licence for project code; third-party packages and data retain their own licences. See `LICENSE`, `THIRD_PARTY_NOTICES.md` and the source records inside each study.
