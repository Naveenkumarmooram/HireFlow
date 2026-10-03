# HireFlow frontend

React + TypeScript browser application. This folder is one independent Vercel project.

## Vercel import

| Setting | Value |
| --- | --- |
| Project name | `hireflow-web` |
| Root Directory | `frontend` |
| Framework | Vite |
| Node.js | 24 |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Environment variable | `VITE_API_URL=https://YOUR-API.vercel.app/api` |

Select **frontend**, not the repository root, when importing from GitHub. Keep “Include source files outside of the Root Directory” disabled; this application has no backend source dependencies.

`VITE_API_URL` is public and compiled into the frontend. Set it before deploying; redeploy after changes. Never add database credentials, JWT secrets or encryption keys here. Those belong only to the backend project.

Routing and browser security headers are defined in `vercel.json`. For a custom API domain, add its exact HTTPS origin to the CSP `connect-src` directive.

## Local development

From this directory:

```sh
npm ci
npm run dev
```

Vite proxies `/api` to the backend at `http://localhost:8000`. Start the backend separately. `.env.example` documents the optional local API setting.

## Checks

```sh
npm run lint
npm test
npm run build
npm run format:check
```

See [the full deployment guide](../docs/DEPLOYMENT.md) for connecting the two projects.
