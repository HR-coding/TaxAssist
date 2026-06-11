# TaxAssist — Frontend

A React + TypeScript + Vite + Tailwind UI for TaxAssist:

- **Landing page** — marketing, features, security, how-it-works.
- **Dashboard** — all of a user's filing **profiles** (self / spouse / dependent), create new ones.
- **Profile workspace** — **all tasks** (prerequisites, schedule checklist, milestones), a live
  **"what the agent is doing"** transparency panel (current state + next *deterministic* step),
  an **agent activity timeline** of durable runs, the computed return, and feedback.

## Run locally

```bash
# 1. Start the backend (from the repo root) on :8080
uvicorn app.main:app --reload --port 8080

# 2. Start the frontend
cd frontend
npm install
npm run dev          # http://localhost:5173
```

In dev, the app calls `/api/*` which Vite proxies to `http://127.0.0.1:8080` (see `vite.config.ts`).

### Auth
The backend enables a **dev-login** fallback whenever `FIREBASE_PROJECT_ID` is unset: the UI sends
`Authorization: Bearer dev:<email>` and the backend trusts it. Just enter any email to sign in.
For production, set `FIREBASE_PROJECT_ID` on the backend and swap `login()` in `src/lib/auth.tsx`
to provide a real Firebase ID token — the rest of the app is unchanged.

### Seeing data
A fresh profile starts empty. Open a profile → **Load demo run** to seed a realistic in-progress
state (verified prerequisites, a Form-16 upload under review, two agent runs) so every panel renders.

## Build

```bash
npm run build        # type-checks, outputs static site to dist/
npm run preview      # serve the production build
```

## Configure the API origin for production

Set `VITE_API_BASE` to your deployed backend before building:

```bash
VITE_API_BASE=https://taxassist.onrender.com npm run build
```

## Hosting (free)

The build output (`dist/`) is a static site — host it free on **Vercel**, **Netlify**, or
**Cloudflare Pages**:

1. Push the repo to GitHub.
2. Import it; set **Root directory** = `frontend`, **Build command** = `npm run build`,
   **Output directory** = `dist`.
3. Add env var `VITE_API_BASE` = your backend URL.
4. Deploy. Then add that frontend URL to the backend's `FRONTEND_ORIGINS` (CORS).
