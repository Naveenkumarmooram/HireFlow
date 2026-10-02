# HireFlow

A recruiter workspace built with React, TypeScript, FastAPI and PostgreSQL. The application supports organisation-scoped jobs, candidates, screening, interviews, offers, tasks, account administration, communication drafts and audit history.

This repository contains the application, migrations, tests and deployment instructions. The obsolete HTML prototype and starter assets have been removed.

## Run locally

Requires Python 3.12+ and Node.js 22.12+ (CI uses Python 3.12 and Node.js 24).

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
Copy-Item backend/.env.example backend/.env
```

Set a generated `JWT_SECRET`, your organisation name, initial admin email and a strong bootstrap password in `backend/.env`. Never commit this file. Generate secrets using Python's `secrets.token_urlsafe(48)` in a trusted local terminal.

```powershell
cd backend
../.venv/Scripts/python build.py
../.venv/Scripts/python -m app.bootstrap
../.venv/Scripts/python -m uvicorn app.main:app --reload --no-access-log --port 8000
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open the URL printed by Vite. Local SQLite is supported for development; PostgreSQL is required in production. Remove bootstrap credentials after provisioning. There is no built-in username or password.

## Validate

From `backend`:

```sh
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip_audit -r requirements.txt
```

From `frontend`:

```sh
npm ci
npm run lint
npm test
npm run build
npm run format:check
npm audit --audit-level=high
```

CI validates both applications and runs the real migration chain against a disposable PostgreSQL 17 database. Local migration tests use a temporary SQLite database unless `TEST_DATABASE_URL` points to an explicitly disposable PostgreSQL test database.

## Structure

- `backend/app/routes/`: business-specific API routes.
- `backend/app/accounts.py`: login, password changes, session revocation and access administration.
- `backend/app/services.py`: tenant lookups, projections and resume processing.
- `backend/app/http.py`: request limits, redacted errors, request IDs and security headers.
- `backend/app/config.py`: validated environment configuration.
- `backend/migrations/`: versioned database changes and frozen historical schema.
- `backend/tests/`: API, security and migration regressions.
- `frontend/src/api.ts`: shared API transport and pagination.
- `frontend/src/AccountSecurity.tsx`: password management.
- `frontend/src/App.tsx`: workspace screens and workflow forms.
- `docs/`: deployment, operations and release requirements.

## Deployment and operating boundaries

Follow [manual Vercel and Supabase deployment](docs/DEPLOYMENT.md), [operations](docs/OPERATIONS.md), and [release requirements](docs/RELEASE_CHECKLIST.md).

Core recruitment workflows are implemented. Email is draft-only; calendar integrations, MFA/SSO, verified-email candidate identity, electronic signatures and automatic retention execution are not implemented. Resume uploads require an external malware scanner and a stable encryption key. Matching is deterministic, does not verify claims and never makes an automatic hiring decision.

Code hardening and passing tests are not an enterprise certification. Complete staging acceptance, PostgreSQL migration verification, restore testing, access review and security review before using real applicant data.
