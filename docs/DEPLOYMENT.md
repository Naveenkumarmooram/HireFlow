# Manual deployment: Vercel and Supabase

Deploy two Vercel projects from the same GitHub repository. Supabase supplies PostgreSQL; the browser talks only to FastAPI. Supabase Auth, Storage and Edge Functions are not used.

## 1. Provision and protect the database

Create separate staging and production Supabase projects. In **Connect**, copy the **Transaction pooler** URI (port 6543). Change its scheme to `postgresql+psycopg://`, URL-encode special characters in the database password, and add `?sslmode=require` (or `&sslmode=require` when a query already exists).

Use a server-only database role that can access application tables. Supabase's project `postgres` connection is compatible with the current setup; never expose that connection string to the frontend. A custom least-privilege runtime role needs explicit server-side RLS policies or an appropriately reviewed bypass-RLS role. Do not assume an arbitrary new role will work.

Migration 0006 enables RLS and revokes public/anonymous/authenticated REST access to the application tables. This prevents the Supabase Data API from bypassing FastAPI authorization. The server connection remains responsible for organisation-scoped authorization. Inspect existing Supabase grants and policies as part of release review. Prefer disabling the Supabase Data API when it is unused.

Enable backups appropriate to your plan and test restoring to a separate project. Do not run production migrations from preview deployments.

## 2. Configure the API environment

Use `backend/.env.production.example` as the key checklist. In the Vercel API project set:

| Key | Value |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | Private Supabase pooler URI with TLS |
| `JWT_SECRET` | Unique random secret, at least 32 characters; recommend 48 random bytes encoded for transport |
| `CORS_ORIGINS` | Exact HTTPS frontend origin; comma-separated for explicitly allowed origins |
| `ACCESS_TOKEN_MINUTES` | `30` |
| `AUTO_MIGRATE_ON_STARTUP` | `false` |
| `RESUME_ENCRYPTION_KEY` | Optional stable Fernet key, required for resume uploads |
| `CLAMD_HOST` / `CLAMD_PORT` | Optional reachable, access-controlled external ClamAV service |

No wildcard CORS. Never put database, JWT or encryption secrets in a `VITE_*` variable.

Generate secrets locally:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store the encryption key in your secret manager and recovery procedure. Losing it makes existing resumes unreadable. Vercel does not provision ClamAV. The app fails closed when scanning or encryption is unavailable. Plain ClamAV TCP must be protected by network controls; do not expose an unauthenticated scanner to the internet.

## 3. Run the controlled database release

Take a backup and rehearse the migration against staging first. On a trusted machine, set the production environment privately in `backend/.env`, install runtime requirements, then run from `backend`:

```sh
python build.py
python -m alembic current
```

Despite its historical filename, `build.py` is an explicit database migration command, not a Vercel build hook. It upgrades to Alembic head and is repeatable. Revision 0006 invalidates all older-format access tokens and refuses ambiguous duplicate user emails. Reconcile duplicates before upgrading; it does not delete or merge identities.

For the first deployment only, additionally set `BOOTSTRAP_ORG_NAME`, `BOOTSTRAP_ADMIN_EMAIL`, and a unique `BOOTSTRAP_ADMIN_PASSWORD` of at least 16 characters in that local environment:

```sh
python -m app.bootstrap
```

The command refuses to create a second bootstrap organisation once users exist. Remove the three bootstrap values afterward. Do not put bootstrap credentials in Vercel. Web startup neither migrates nor creates users.

## 4. Configure the Vercel API project

- Repository: `Naveenkumarmooram/HireFlow`.
- Root Directory: `backend`.
- Framework: FastAPI (entrypoint declared in `pyproject.toml`).
- Python: 3.12, pinned by `.python-version`.
- **Clear any old Build Command override such as `python build.py`.** Leave Build Command, Install Command and Output Directory on framework defaults.
- Set the production environment values from step 2, then deploy.
- Check `https://YOUR-API.vercel.app/api/live` and `/api/health`. The latter checks the database.

The existing linked project name is `hireflow-api`. Local `.vercel` metadata is ignored; importing from GitHub does not require it.

## 5. Configure the frontend

- Root Directory: `frontend`.
- Framework: Vite.
- Node.js: 24.
- Install Command: `npm ci`.
- Build Command: `npm run build`.
- Output Directory: `dist`.
- Production variable: `VITE_API_URL=https://YOUR-API.vercel.app/api`.

Set the API address before building; changing it requires a redeployment. SPA rewrites and security headers are in `frontend/vercel.json`. The CSP permits Vercel API subdomains. If using a custom API domain, add its exact HTTPS origin to `connect-src` in that file before deployment.

The existing linked frontend project is `hireflow-web`. Copy its final origin into API `CORS_ORIGINS` and redeploy the API if that value changed. Preview projects must use separate staging data and secrets.

## 6. Accept the release

Sign in, change the bootstrap password through Account security, add a recruiter and interviewer, create a job and candidate, schedule an interview, approve an offer, and verify disabled users lose access. Confirm an interviewer cannot access offers or unassigned candidates. Test expired links, logout, browser reload, CORS PUT requests and unavailable API behavior.

Configure Vercel firewall/bot controls for login and public application routes. Database-backed account throttling is implemented, but it does not replace edge protection against distributed abuse or random-account attempts.

Avoid recording full URLs in provider access logs: offer and candidate links contain bearer tokens. Application logs use route templates and never log request bodies or token values.

References: [Vercel FastAPI](https://vercel.com/docs/frameworks/backend/fastapi), [Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres), [prepared statements](https://supabase.com/docs/guides/troubleshooting/disabling-prepared-statements-qL8lEL).
