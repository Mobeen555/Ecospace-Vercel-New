# Deploy EcoScope AI 3.0 to Vercel

This guide deploys the complete new project: a JavaScript frontend, Python analysis/API and five CrewAI roles powered by Groq. Keep your working Streamlit project as a separate repository.

## 1. Extract the ZIP and create a new GitHub repository

1. Download and extract `EcoScope_AI_Vercel_v3.0.zip`.
2. Open the extracted `ecoscope_vercel` folder. At its top level you should see `package.json`, `requirements.txt`, `pyproject.toml` and `vercel.json`, alongside `api`, `backend`, `web` and `supabase` folders.
3. On GitHub, create a **new repository**, for example `ecoscope-ai-vercel`.
4. Upload **all the contents inside that folder**, preserving subfolders. GitHub Desktop is convenient for this. Do not upload only the ZIP or only one Python file.
5. Commit the upload. Check that GitHub shows `backend/evidence.py` and all five `backend/agents/*.py` files. This prevents the missing-module errors from partial uploads.
6. Keep `.env` and all API keys out of GitHub. The included `.gitignore` handles normal local secrets and generated folders.

There is no Streamlit main-file setting here. Vercel builds `web/` and loads the backend through **`api/index.py`** using the supplied configuration.

## 2. Create the Supabase project

1. Sign in at https://supabase.com/dashboard and create a project. Use a region reasonably close to your users and Vercel function region.
2. Wait until the database is ready.
3. Open **SQL Editor**, create a new query, and paste the entire contents of **`supabase/setup.sql`**.
4. Run the query. It creates `ecoscope_runs`, `ecoscope_limits`, the update/locking functions, a geocoding rate gate and the **private** `ecoscope-private` storage bucket.
5. Check **Storage**: the bucket should exist and should not be public.
6. Find the project's **Project URL** and **legacy `service_role` key** in its API settings. This app uses the service-role key on the Python server. Do not substitute the anonymous/publishable key, and never expose the service-role key in frontend code.

The SQL can be rerun. It does not delete existing studies. Leave the bucket name unchanged unless you also change `SUPABASE_BUCKET` and the SQL bucket definition.

## 3. Obtain a Groq API key

1. Open https://console.groq.com/keys and create a key.
2. Check the models available to your account at https://console.groq.com/docs/models.
3. The supplied default is **`openai/gpt-oss-120b`**. Set `GROQ_MODEL` to another supported text/reasoning model only after testing its CrewAI tool-use behaviour.
4. Check your account's actual limits at https://console.groq.com/docs/rate-limits and in the console. The code's conservative token budget is configurable; it cannot increase your provider quota.

Groq credentials stay on the server. Users explicitly consent before study summaries, coordinates and requested statistics are sent to the model. Raw raster files are not sent to Groq.

## 4. Prepare two private workspace secrets

Choose a long, unique workspace password (minimum 12 characters). Then generate a random signing secret using Python:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Keep both values private. The password lets invited users open a workspace. The signing secret protects their cookies. Each browser has its own study list; this is not a shared team account or a replacement for a full identity system.

## 5. Import the repository into Vercel

1. Sign in at https://vercel.com and choose **Add New → Project**.
2. Connect/import `ecoscope-ai-vercel`.
3. Set **Framework Preset: Vite**. Keep it Vite even though Python/FastAPI is also present.
4. Set **Root Directory** to the directory containing `vercel.json` and `package.json`. If you uploaded the folder contents directly to the repository root, leave the root as `./`. If GitHub has an extra `ecoscope_vercel/` wrapper, select that directory instead.
5. Confirm the build settings below. They are already defined in `vercel.json`.

| Setting | Value |
|---|---|
| Framework | Vite |
| Install command | `npm ci` |
| Build command | `npm run build` |
| Output directory | `dist` |
| Node.js version | `24.x` |
| Python version | **3.12**, selected by `.python-version` / `pyproject.toml` |
| Python entrypoint | `api/index.py` |
| Function duration | 300 seconds per request, supplied in `vercel.json` |

Enable **Fluid compute** in the project's function settings if it is not already enabled. This scientific/CrewAI dependency stack is too large for a standard small Python function bundle. It uses **Large Functions, currently a public beta**, which supports eligible bundles up to 5 GB. The enabling environment variable is included below. Availability and platform limits should be checked for your Vercel account.

Official references: https://vercel.com/docs/functions/runtimes/python and https://vercel.com/changelog/vercel-functions-can-now-be-up-to-5-gb-in-package-size . Large Functions require Fluid compute and currently exclude Secure Compute/Static IP configurations. If your account cannot enable this option, this exact all-Vercel backend cannot be deployed there; use a compatible hosting plan/runtime before proceeding.

## 6. Add environment variables before deploying

In Vercel's environment-variable section, add each variable separately. Apply them to **Production** and to **Preview** if you will test preview deployments. Prefer a separate Supabase project and credentials for previews of untrusted branches.

| Variable | Value to enter |
|---|---|
| `APP_ACCESS_PASSWORD` | Your unique password, at least 12 characters |
| `SESSION_SECRET` | The random value generated above, at least 32 characters |
| `SUPABASE_URL` | `https://YOUR_PROJECT.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Your server-side legacy `service_role` key |
| `SUPABASE_BUCKET` | `ecoscope-private` |
| `GROQ_API_KEY` | Your Groq API key |
| `GROQ_MODEL` | `openai/gpt-oss-120b` |
| `GROQ_TOKENS_PER_MINUTE` | `6000` initially; adjust to your actual account/model quota if needed |
| `VERCEL_SUPPORT_LARGE_FUNCTIONS` | `1` |
| `ECOSCOPE_LOCAL` | `0`, or omit it |

Do **not** add `VITE_` to secret names. Vite variables with that prefix can enter the public JavaScript bundle. Do not put these values in `vercel.json` or GitHub.

`APP_ORIGINS` can be omitted for production: the frontend and API share one origin. Its localhost examples in `.env.example` are for local development only. `ECOSCOPE_DATA_DIR` is also local-only. Do not upload `.env` to Vercel; use its environment settings.

## 7. Deploy and verify your own cloud connections

1. Click **Deploy**. The first build can take several minutes because Python GIS and CrewAI dependencies are substantial.
2. Confirm that the build succeeds and the deployment shows a Python function for `api/index.py` using the large-function path.
3. Open your new URL. The overview should appear with the charcoal globe illustration and ivory/lime interface.
4. If a setup notice lists missing variables, correct them and **redeploy**. The `/api/status` endpoint reports configuration status, never secret values.
5. Click **New study**, enter the workspace password, and start with the default Rawal Lake coordinates, **Climate + Air quality**, and a historical end date at least eight days ago.
6. Check that source dates and methods appear in **Analysis**. A provider outage should produce an unavailable-source notice, not substituted values.
7. Open **AI studio**, enter a focused question, tick the data-sharing consent and choose **Run five-agent review**. Confirm five completed notes and a cited final briefing.
8. In **Reports**, choose whether to include the AI review, generate the package, and download PDF, HTML, Excel and ZIP. The links redirect to short-lived, private Supabase download URLs.
9. Refresh the browser. The saved study should restore. The browser resumes additional steps only when you ask it to; it is not an autonomous background worker.
10. Try a small separate satellite study (1–2 km radius, a recent historical month, initially one scene). Check the acquisition date, usable coverage, true-colour layer and indices. Cloudy/unsuitable scenes can correctly produce no water-quality result.

**These account-level checks are required:** the supplied package was tested locally, but no real Groq key, Supabase service key or Vercel project access was provided for an authenticated cloud deployment.

## 8. Understand progress, limits and saved studies

- Each environmental module runs in a separate request. Satellite catalogue retrieval and each selected scene are separate saved steps. Each CrewAI role is also a separate saved step.
- Pause stops after the current step completes. Refreshing/closing the page stops the browser's progression; already committed steps remain saved.
- If a step times out, click **Refresh**, wait for the six-minute update lease to expire if necessary, then resume. Completed agent stages are not rerun. A stage that called Groq but failed before committing may incur another model call on retry.
- Start with small areas and short windows. Satellite processing is capped at 250 km², six scenes and a three-year search window. Catalogue and observation retrieval caps are documented in `METHODS.md`.
- Browser maps show at most 2,000 observation points with a notice when capped. Full returned records remain in data/GeoJSON exports. Tables show previews and support 100-row browsing.
- API uploads are capped below Vercel's request size limit; use field CSV files under 2 MB and boundaries under 400 KB. Generated private objects are limited to 48 MB each in this app.
- The workspace cookie lasts 30 days. Deleting cookies, rotating `SESSION_SECRET` or using a different browser does not recover the prior study list. Download your evidence ZIP. This version has no account recovery or cross-device access.
- Supabase storage has no automatic retention policy in this release. Regenerated exports and objects from interrupted saves can remain. Review usage periodically and remove obsolete objects through Supabase Storage; remove their corresponding study metadata only when intentionally retiring the study. Do not delete active snapshot objects.

## Troubleshooting

| Symptom | What to check |
|---|---|
| `ModuleNotFoundError: backend` / `evidence` | Upload the complete project structure and choose the correct root. Do not add the project's own modules to pip requirements. |
| Python bundle too large | Confirm Fluid compute and `VERCEL_SUPPORT_LARGE_FUNCTIONS=1`; redeploy. Large Functions must be available for the project. |
| Frontend opens but API returns 404 | Keep Framework Preset **Vite**, restore `vercel.json`, and check that `api/index.py` exists at the selected root. |
| Build uses wrong Python | Keep `.python-version` and `pyproject.toml`; this project targets **3.12**. |
| Supabase HTTP 401/403/404 | Check the URL, server `service_role` key, private bucket and completed SQL setup. Do not make the bucket public to fix it. |
| Supabase table/function missing | Run the complete supplied SQL in the same project referenced by `SUPABASE_URL`. |
| AI studio says connection unavailable | Add a real `GROQ_API_KEY`, confirm the model is enabled and redeploy. |
| Groq 429 / token budget message | Wait and resume; check account limits. Adjust the local budget only within your real quota. A shorter question/smaller study also reduces context. |
| Function timeout / study busy | Refresh; allow the lease to expire, then resume. Reduce scene count, area or date window on a new study if the same source repeatedly exceeds the duration. |
| Blank water layer | Inspect acquisition/coverage and water-pixel count. No usable water pixels means water interpretation is unavailable. |
| Grey basemap | Browser access to OpenStreetMap tiles may be blocked/rate-limited. A notice appears; source overlays and report maps remain available. |
| Old studies missing | Confirm the same browser and unexpired cookie. This MVP has browser-session ownership, not login-based account recovery. |

For a broadly shared service, add real account authentication, per-user quotas, a retention policy and centrally enforced login/AI rate limits. The included login limiter and Groq pacing are process-local; Vercel can run more than one instance. Keep the workspace password limited to trusted research users and use Vercel Firewall rules for distributed protection where available.

## Costs, data terms and credits

Open libraries and public endpoints have separate usage conditions. The code licence does not grant free hosting, AI or data redistribution.

- Vercel plans and limits: https://vercel.com/docs/plans and https://vercel.com/docs/functions/limitations
- Supabase plans/quotas: https://supabase.com/pricing
- Groq models and limits: https://console.groq.com/docs/models and https://console.groq.com/docs/rate-limits
- Open-Meteo free endpoint terms, including non-commercial usage conditions: https://open-meteo.com/en/terms
- OpenStreetMap tile policy: https://operations.osmfoundation.org/policies/tiles/
- Nominatim policy: https://operations.osmfoundation.org/policies/nominatim/ . This app uses explicit searches, caching and a shared cloud gate; no autocomplete or bulk geocoding.
- GBIF record licences and dataset attribution remain in returned tables: https://www.gbif.org/terms

Do not advertise unlimited free use, guaranteed accuracy or official emergency predictions. Review provider licensing and replace endpoints/hosting arrangements as needed before commercial or high-volume deployment.

## Troubleshooting the AI studio (v3.1 fixes)

| What you see | Cause | Fix |
|---|---|---|
| "The API did not return a readable response" only when a review step runs | `import crewai` writes to `~/.local/share/crewai`, which is read-only on Vercel | Fixed in `backend/crew_config.py` (`ensure_writable_home`) — HOME is redirected to `/tmp` |
| Same message, with a specific hint about *timeout*, *crash* or *Deployment Protection* | Vercel answered with its own error page | Follow the hint; open **Vercel → Deployment → Logs** and read the traceback for `/api/index` |
| "This study is busy or has changed…" | A step was killed by Vercel (timeout/crash) and its lock is held for up to six minutes | Wait, press **Refresh**, then **Resume saved review** |
| "Review paused: the model kept attempting a native tool call…" | gpt-oss answered with a native tool call (Groq `400 tool_use_failed`) twice in a row | Resume the stage; the adapter normally recovers the call automatically |
| "Groq's token-per-minute window is full…" / "rate or token limit" | Your Groq tier's TPM is lower than one agent stage needs | Wait a minute and resume, or set `GROQ_TOKENS_PER_MINUTE` to your real limit from the Groq console |
