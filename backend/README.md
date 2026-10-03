# HireFlow backend

FastAPI API, authentication, recruitment workflows and PostgreSQL persistence. This folder is one independent Vercel project. Supabase hosts the database; it does not deploy this Python application.

## Vercel import

| Setting | Value |
| --- | --- |
| Project name | `hireflow-api` |
| Root Directory | `backend` |
| Framework | FastAPI |
| Python | 3.12 (`.python-version`) |
| Entrypoint | `app/main.py` (`pyproject.toml`) |
| Build / Install / Output overrides | Leave unset; use framework defaults |

Select **backend**, not the repository root. Keep “Include source files outside of the Root Directory” disabled; the API has no frontend source dependencies. `vercel.json` explicitly selects FastAPI.

Clear any existing dashboard build command that runs `python build.py` or migrations. Database migrations are a separate release operation.

## Environment

Use `.env.production.example` for the complete list. Required production values:

- `ENVIRONMENT=production`
- `DATABASE_URL`: private Supabase PostgreSQL pooler URI using `postgresql+psycopg://` and TLS.
- `JWT_SECRET`: unique random secret of at least 32 characters.
- `CORS_ORIGINS=https://YOUR-FRONTEND.vercel.app`
- `AUTO_MIGRATE_ON_STARTUP=false`

Database and signing secrets belong only in this project. Resume uploads also require scanner configuration and a stable encryption key.

## Database setup and local development

From this directory, with your virtual environment active:

```sh
python -m pip install -r requirements-dev.txt
# Copy .env.example to .env and configure secrets and initial admin values.
python migrate.py
python -m app.bootstrap
python -m uvicorn app.main:app --reload --no-access-log --port 8000
```

`migrate.py` upgrades the schema explicitly. `app.bootstrap` provisions the initial admin once. Neither runs during a Vercel build or API startup. Remove bootstrap credentials after provisioning.

Production migration, backup and bootstrap instructions: [deployment guide](../docs/DEPLOYMENT.md).

## Checks

```sh
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip_audit -r requirements.txt
```

After deployment, check `/api/live` and `/api/health`; health verifies the database connection.
