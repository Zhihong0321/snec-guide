# Deploy SNEC 2026 Guide on Railway (Docker + GitHub)

## Prerequisites

- GitHub repository with this code (no `.env` committed — it is gitignored)
- [Railway](https://railway.app/) account
- PostgreSQL database with `snec26_exhibitors` and visit-log tables (run `db_setup.py` locally once against the same DB)

## 1. Push to GitHub

```bash
git init
git add .
git commit -m "Add Railway Docker deployment"
git branch -M main
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

## 2. Create Railway project

1. **New Project** → **Deploy from GitHub repo** → select your repository.
2. Railway detects `Dockerfile` and `railway.toml` (Docker build, health check on `/api/health`).
3. Add a **PostgreSQL** plugin (or use an existing Railway Postgres).
4. On the **web service**, open **Variables** and set:

| Variable | Required | Notes |
|----------|----------|--------|
| `DATABASE_URL` | Yes | Reference `${{Postgres.DATABASE_URL}}` from the Postgres service |
| `OPENAI_API_KEY` | Yes* | MiniMax / OKAI gateway key |
| `OPENAI_BASE_URL` | No | Default `https://www.okaoi.com/v1` |
| `OPENAI_MODEL` | No | Default `MiniMax-M2.7` |
| `DEFAULT_CHAT_MODEL` | No | Same as `OPENAI_MODEL` if unset |
| `UNIAPI_KEY` | Yes* | For Gemini model in chat |
| `UNIAPI_BASE_URL` | No | Default `https://api.uniapi.io` |
| `GEMINI_MODEL` | No | Default `gemini-3.1-flash-lite` |
| `ENABLE_WEB_SEARCH` | No | `true` / `false` (default on) |

\*At least one of `OPENAI_API_KEY` or `UNIAPI_KEY` depending on which models you use.

`PORT` is set automatically by Railway — do not override it.

## 3. Networking

- Railway assigns a public URL (e.g. `https://your-app.up.railway.app`).
- Optional: add a custom domain under **Settings → Networking**.

## 4. Verify

```bash
curl https://YOUR_APP.up.railway.app/api/health
```

Expect `"ok": true` and `"database_configured": true` when `DATABASE_URL` is set.

## Notes

- **Uploads** (`/uploads`) use the container filesystem. They are lost on redeploy unless you add a [Railway volume](https://docs.railway.app/guides/volumes) mounted at `/app/uploads`.
- **Floor plan images** go in `floor_plans/` in the repo (or mount a volume at `/app/floor_plans`).
- Local dev: `python run_web.py` (opens browser on localhost). Production uses the Dockerfile `uvicorn` command on `0.0.0.0`.

## Rotate credentials

If database URLs were ever committed, rotate the Postgres password in Railway and update `DATABASE_URL` on all services.
