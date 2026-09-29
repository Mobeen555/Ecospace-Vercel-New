# Validation record · EcoScope AI 3.0

Checked 29 September 2026. This records completed checks and their limits; it is not a certificate of scientific validity or a claim of authenticated cloud deployment.

## Completed

- **42 Python tests passed**, using Python 3.12 and the pinned direct dependencies. Coverage includes geodesic area/coordinate order, missing values, partial climate months, reflectance scale/offset and nodata, CSV units/filtering, separate trophic indices, formula-injection protection, source failures, exactly five agent roles, scoped tools, actual CrewAI execution with controlled Groq responses, rate/truncation stops, stale-review rejection, report formats, authentication/origin checks, browser-owner isolation, revision conflicts, lease release, snapshot round trips, table pagination, raster reprojection, Supabase REST request contracts, and saved satellite scene sequencing.
- **6 frontend tests passed**: domain/agent configuration, missing numeric values, historical defaults, bubble sizing, CSV formula protection and timezone-stable chart date parsing.
- **Production frontend build passed** with Vite 8.3.1 and Node.js 24.19.0. Fonts are bundled locally; no Google Fonts request is needed.
- **Headless Chromium workflow passed** with a local FastAPI server: login, create study, partial provider failure, charts, all five AI stages, PDF download, refresh restoration and navigation across all five pages at **390, 768 and 1440 pixels**. Final run reported no JavaScript page errors and no document horizontal overflow in these 15 responsive page checks.
- Desktop, study-form, analysis, AI-studio and mobile screenshots were inspected. A narrow-screen heading clip and a Leaflet navigation race found during review were corrected.
- `vercel.json` fields validated against the retrieved official configuration schema. This does not substitute for an actual Vercel deployment.
- Real connector smoke checks succeeded for Rawal Lake: **31 historical daily records**, **7 forecast daily records**, **120 hourly air-quality records**, and **1 earthquake catalogue event** in the configured nearby search window. Historical dates were August 2026; forecast dates were supplied by providers at retrieval. These counts describe the smoke check, not a complete assessment of the lake. See `docs/live-connector-check.json` for dates and providers.

The Python run emits deprecation warnings from the pinned CrewAI and geospatial dependencies. The tested workflows passed despite these warnings; upgrading dependencies should repeat the relevant integration checks.

## Not verified with real cloud credentials

No live Groq API key, Supabase service-role key or Vercel project access was supplied. Therefore:

- Groq network calls in agent integration/browser tests were controlled responses. The tests exercised the real CrewAI execution and tools, but not your account's model permissions, quota, latency or output quality.
- Supabase REST shapes were tested with controlled responses; live SQL execution, RLS/service-role access and signed-download behaviour still require the deployment guide's account checks.
- Vercel build/bundle eligibility, actual ASGI routing, cold-start latency, duration and memory under your chosen plan have not been measured on a deployed project.
- This migration's live smoke test did not revalidate every remote data provider or download/process a new Sentinel-2 scene. Satellite core processing/regression and saved-stage handling were tested with local synthetic fixtures. Verify a small real satellite study after deployment.
- OpenStreetMap basemap tiles were unavailable in this browser-test environment. Boundary overlays and explicit failure notices were checked. Tile reachability must be checked in your deployed browser; no claim of live tile validation is made.
- No stress/load test, enterprise identity audit, calibrated environmental hazard validation or end-to-end government operational acceptance was performed.

Test fixtures are excluded from the Vercel runtime bundle and are never loaded by the normal application. This is a functional research MVP with a polished frontend, not an official disaster-warning system.
