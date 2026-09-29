# EcoScope Vercel architecture

## Request and persistence model

Vite builds the frontend into `dist`. Vercel serves those files and routes `/api/*` to `api/index.py`, which exposes a FastAPI ASGI application. The explicit Vite preset preserves file-based Python functions instead of promoting the entire repository to a Python-only framework preset.

The API authenticates a signed, HttpOnly browser cookie, validates parameters and looks up runs by both random owner ID and UUID. A private Supabase bucket stores ZIP snapshots containing JSON tables and NumPy arrays, with pickle disabled. Postgres stores the current snapshot path, version, summary and a six-minute lease.

A mutation atomically claims the expected revision. It computes one step, writes a fresh snapshot object, and commits the new object path with compare-and-set semantics. Concurrent/stale requests receive HTTP 409. A failed computation releases the lease; an interrupted function leaves a lease that expires. Successfully committed old snapshots are deleted on a best-effort basis. Cloud storage is authoritative; local function memory and `/tmp` are not durable storage.

The browser advances the queue with sequential HTTP requests. There are no threads expected to keep running after a Vercel response. Each satellite scene is its own invocation; first/latest raster arrays are retained for change analysis, and all processed scene summaries remain. Environmental adapters maintain bounded, process-local caches of public provider data, with original retrieval timestamps retained.

## Five agents, not five separate servers

| Order | Agent file | Evidence scope |
|---|---|---|
| 1 | `coordinator.py` | Scope, source inventory, quality checks |
| 2 | `climate_air.py` | Climate, air quality, river outlook, official US weather alerts |
| 3 | `geospatial_water.py` | Satellite/water screening and earthquake catalogue |
| 4 | `ecology_field.py` | Biodiversity and uploaded field observations |
| 5 | `reviewer_reporter.py` | All saved notes and evidence checks; final report synthesis |

The coordinator note is passed to specialists; the final reviewer receives all four completed notes. Each request creates a real CrewAI Agent/Task/Crew with one active role, using `Process.sequential`. After it completes, its output is persisted before the next role starts. This implements five sequential persisted stages without relying on one long function invocation. There is no extra manager, planner, delegation agent, unrestricted code executor or web-browsing agent.

The Groq adapter strips unsupported cache metadata, sends only permitted message fields, bounds calls/output/time, and keeps the credential private. Approved tools read scoped evidence and calculate allowed statistics from saved tables. Tool activity and usage are retained. The model sees summaries and requested tabular statistics, not satellite pixels.

Each stage has a 180-second model time budget and six-call ceiling within a 300-second function setting. These limits cannot guarantee success under every provider/network delay. Previous stages remain available after a failure. Groq/account rate limiting can still pause a stage.

## Scientific integrity

The Python engine remains the calculator. AI writes interpretations, not source measurements. Fingerprints include study parameters, source records, facts, metrics and actual table contents. Adding field measurements clears the existing review and export links. Current complete reviews can be included in reports; incomplete/stale reviews cannot.

Browser overlays are reprojected to geographic coordinates before Leaflet placement. Export GeoTIFFs retain their documented UTM CRS/nodata. Browser charts transmit relevant plotted columns, preserve nulls and use temporal axes for dated data. Historical dates and forecast dates remain distinct. Full returned records remain available in exports, subject to explicit retrieval caps.

## Security and operational boundary

Secrets are server-only environment variables. No `VITE_` secret variables, public Supabase bucket, client service-role token or credential entry form is used. Source/user strings render as text, reports escape markup, and CSV/Excel formula prefixes are neutralised. Mutating browser requests require the same origin or an explicitly configured local origin.

This is a password-protected research MVP. The service role bypasses database RLS; every API lookup must therefore enforce owner isolation, as tested. There is no email identity, workspace sharing, retention scheduler, organization role management or recovery token. The basic login and AI-rate budgets are per process. Before public institutional rollout, replace browser-session ownership with a proper identity system, add distributed quotas and validate data-science use cases with domain experts.

## Reports

Matplotlib/report rendering is guarded within a server instance. Reports are generated from saved data and uploaded to private Storage. Downloads redirect to expiring Supabase URLs rather than returning large binaries through Vercel's API payload limit. PDF/HTML show table previews; Excel/CSV/GeoJSON contain the full returned records. The archive also contains the available latest satellite GeoTIFF, source metadata, figures and any included current AI review.

The storage interfaces support SQLite/files for local development only. On Vercel, local mode is always disabled even if `ECOSCOPE_LOCAL=1` was mistakenly set.
