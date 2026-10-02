# Amiro HireFlow AI

HireFlow is Amiro Tech Solutions' recruiter workspace for managing jobs, applicants, screening, interviews and offers in one hiring pipeline. This repository contains the original HTML reference prototype and a new React + FastAPI + PostgreSQL application foundation.

https://amiro-hireflow-poc.naveenmooram111.chatgpt.site

## Current implementation

- Responsive React/TypeScript recruiter workspace and mobile secondary-navigation menu
- Argon2 password hashes, signed access tokens, organisation-scoped data, recruiter/admin/coordinator/interviewer permissions, and admin-managed users
- PostgreSQL/Alembic schema for tenants, users, jobs, job requirements, applications, candidates, scores/evidence, screenings, interviews/feedback, offers, tasks, communication templates/outbox, audit history, settings, and encrypted resumes
- Job requisitions, weighted must-have/nice-to-have requirements, publish/close flow, public careers page, consent-based applications, duplicate detection, private candidate status/withdrawal link
- Candidate intake, filters/sorting, full stage vocabulary, telephone screening, audit-backed activity, deterministic profile matching with evidence notes, and interview scheduling/scorecards
- Resume-first bulk intake creates or matches candidate profiles automatically, associates them with a role, and flags missing contact/profile fields for recruiter review
- Offer drafts, approver workflow, private candidate offer link and acceptance/decline decisions
- Recruiter tasks, team directory/RBAC, organisation settings, audit log, communication templates and unsent draft outbox
- Resume upload path for PDF/DOCX with signature/size/duplicate checks, ClamAV scanning, Fernet-encrypted database storage, conservative local text/skill extraction, and authenticated download
- Recruiter data refreshes every 10 seconds while the tab is visible
- Vercel deployment configuration for a Vite frontend and FastAPI serverless API, backed by Supabase PostgreSQL

The original `dist/index.html` is retained as a UI reference, not the active app. Matching is deterministic and uses self-reported or resume-extracted profile skills until recruiter verification; it is not AI and never makes a hiring decision. Resume extraction supports text-based PDF/DOCX only, not OCR or an LLM. Email templates and personalized drafts work, but nothing is sent. Interviews are persisted, but calendar events and meeting links are not created. Offer approval/acceptance works, but generated signed offer documents and notification delivery are not connected.

Resume upload fails closed unless both ClamAV is reachable and `RESUME_ENCRYPTION_KEY` is valid. Extracted skills/experience are candidate-provided document text and remain unverified. Vercel does not run the Compose ClamAV service; configure a reachable external ClamAV service before enabling resume uploads, otherwise resume intake will remain disabled. The current local preview uses temporary SQLite and also has scanning/key settings unset.

## Deploy with Vercel and Supabase

The repository is prepared as two Vercel projects connected to one GitHub repository:

1. Create a Supabase project and wait for its database to finish provisioning.
2. In Supabase, open **Project Settings → Database → Connection string → Transaction pooler**. Use the URI with port `6543`, add `sslmode=require`, and use the SQLAlchemy driver prefix `postgresql+psycopg://`.
3. In Vercel, import `Naveenkumarmooram/HireFlow` as the API project and set its **Root Directory** to `backend`. Vercel detects the FastAPI entrypoint from `backend/pyproject.toml`; `backend/build.py` applies Alembic migrations during deployment.
4. Add the backend environment variables below to the API project for the appropriate Production/Preview environments. `DATABASE_URL` must be available during build so migrations can run.
5. Deploy the API and copy its Vercel domain.
6. Import the same GitHub repository as a second Vercel project for the frontend, with **Root Directory** `frontend`.
7. Set the frontend variable `VITE_API_URL` to `https://YOUR-API-DOMAIN/api`, then deploy.
8. Copy the final frontend domain into the API project's `CORS_ORIGINS` (comma-separated if allowing more than one origin) and redeploy the API.

API project environment variables:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Supabase Transaction Pooler URI using `postgresql+psycopg://`, port `6543`, and `sslmode=require` |
| `JWT_SECRET` | Random, unique secret of at least 32 characters |
| `BOOTSTRAP_ORG_NAME` | `Amiro Tech Solutions` or your organization name |
| `BOOTSTRAP_ADMIN_EMAIL` | Your initial admin login email |
| `BOOTSTRAP_ADMIN_PASSWORD` | Unique strong initial admin password |
| `AUTO_MIGRATE_ON_STARTUP` | `false` (migrations run in the Vercel build step) |
| `CORS_ORIGINS` | The exact deployed frontend origin, for example `https://hireflow-web.vercel.app` |
| `RESUME_ENCRYPTION_KEY` | Optional until resume scanning is provisioned; keep stable and secret once used |
| `CLAMD_HOST` / `CLAMD_PORT` | Optional external ClamAV service; without it resume uploads stay disabled |

Generate a Fernet key locally if you have configured an external malware scanner:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set it as `RESUME_ENCRYPTION_KEY` in Vercel. Losing the key makes stored resumes permanently unreadable. Never commit secrets or paste them into chat.

After deployment, verify `https://YOUR-API-DOMAIN/api/health`, then open the frontend Vercel URL. The bootstrap account is the `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` configured above. Change these values before first deployment; they are not safe defaults.

**What will work without further integrations:** recruiter accounts, jobs, applications, candidate pipeline, screenings, interview records/feedback, tasks, offers, and audit-backed workflow data persist in Supabase PostgreSQL. Resume upload remains disabled without an external scanner and encryption key. Email delivery, Google/Microsoft calendar, SSO/MFA, and OCR/AI are not configured by connecting Vercel and Supabase alone.


## Local development without Docker

Configure `backend/.env` from `backend/.env.example` with a PostgreSQL connection string. Start FastAPI and the Vite app in separate terminals:

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

The Vite development server proxies `/api` to `http://localhost:8000`. Backend regression tests: `cd backend; python -m pytest -q`. Frontend checks: `cd frontend; npm run build; npm run lint`.

## Product scope

- Role-based recruiter, hiring-manager and interviewer access
- Job publishing and company careers portal
- Candidate pipeline, secure resume intake and explainable match scoring
- Telephone screening with CCTC, ECTC, notice period, relocation and contract preference
- Technical Round 1 and Round 2 scheduling and feedback
- Google Calendar/Meet and Microsoft Outlook/Teams integration screens
- Email invitations and reminders
- Offer workflow, access permissions and audit-log experience

The items below define the full HireFlow vision. Implemented portions are listed under Current implementation. Remaining production scope includes password reset/MFA/SSO, application questionnaire configuration and attachments, OCR, deeper candidate deduplication/merge and talent pools, verified evidence levels, fairness monitoring, interview self-scheduling/calendar/meeting providers, real email delivery and templates editing/audit policies, generated/e-signed offer documents, hiring-manager scorecard comparison, retention/deletion automation, exports, full audit for every sensitive operation, and production-grade tenant provisioning/billing.

## Recommended production stack

- Frontend: React + TypeScript
- Backend: FastAPI or Node.js/NestJS
- Database: PostgreSQL
- Resume storage: S3-compatible object storage
- Queue: SQS, Redis Queue or equivalent
- Authentication: organisation accounts with RBAC, password reset, MFA and optional Google/Microsoft SSO
- Email: AWS SES, Microsoft Graph or Gmail API
- Calendar/meetings: Google Calendar API + Meet; Microsoft Graph + Teams
- AI extraction/scoring: document parser plus LLM/embedding service with evidence-linked scoring

## Suggested services

1. Identity and organisation management
2. Job and careers-site publishing
3. Candidate and resume management
4. Resume extraction and scoring
5. Screening and recruitment workflow
6. Interview scheduling and feedback
7. Communication and templates
8. Offer management
9. Audit, reporting and administration

## Essential API groups

- `/auth` — sign-in, refresh, password reset, MFA and SSO callbacks
- `/organisations` and `/users` — members, roles and permissions
- `/jobs` — job descriptions, requirements, publishing and closure
- `/applications` — public application form and source tracking
- `/candidates` — profile, resume, compensation, availability and timeline
- `/scoring` — extraction, match score, criteria and evidence
- `/interviews` — rounds, panel, slots, meeting links and feedback
- `/communications` — templates, email delivery and reminders
- `/offers` — approvals, document generation, sending and acceptance
- `/integrations` — Google, Microsoft, careers website and email provider
- `/audit-events` — security and business audit history

## Integration setup required

### Google Workspace

- Google Cloud project
- OAuth client ID and secret
- Calendar/Gmail scopes
- Approved redirect URL
- Recruiter consent and token storage

### Microsoft 365

- Microsoft Entra application
- Client ID, tenant ID and secret/certificate
- Microsoft Graph Calendar/Mail/OnlineMeetings permissions
- Approved redirect URL

### Company careers website

- Preferred: careers subdomain served by the product
- Alternative: embedded jobs widget plus secure applications API
- Webhook/API key for synchronisation
- CAPTCHA, consent statement and attachment validation

### Email

- Verified company sender domain
- SPF, DKIM and DMARC
- Delivery, bounce and complaint webhooks

## Important production controls

- Encrypt resumes and tokens at rest
- Store OAuth tokens only on the server
- Validate file type, size and malware status
- Keep AI scoring explainable and recruiter-controlled
- Do not score protected personal characteristics
- Maintain consent, retention and deletion workflows
- Log candidate exports, deletions, role changes and offer approvals
- Back up the database and test recovery

## Recommended implementation order

1. Authentication, organisation, users and RBAC
2. Jobs, careers page and candidate applications
3. Candidate pipeline and resume storage
4. Resume extraction and evidence-based scoring
5. Screening and interview workflow
6. Email and calendar integrations
7. Offers, approvals and audit logs
8. Reporting, automation and multi-tenant SaaS hardening

## Next production milestones

1. Provision Supabase and Vercel projects, rotate development credentials, and verify database backups and deployment environments.
2. Replace the bootstrap-only account flow with organisation signup, invitations, password reset, MFA/SSO, password rotation and user deactivation.
3. Add real email delivery and Google/Microsoft OAuth-backed calendar/meeting creation; test bounce, retry, token revocation and consent handling.
4. Add OCR and richer resume extraction with user verification, evidence provenance, parser confidence, and fairness/override monitoring.
5. Add signed document generation, e-signature, candidate questionnaires, configurable scorecards and pipeline gates.
6. Implement scheduled retention/deletion, export, backup/recovery, secret rotation, monitoring and production deployment controls.

Before real recruiter use, rotate all development secrets, provision organization users through an admin workflow, add automated migrations, enforce production HTTPS/rate limits/backups, and complete privacy/retention/audit controls. Then build jobs/applications and secure resume handling, followed by real email/calendar, interviews, offers and reporting.
