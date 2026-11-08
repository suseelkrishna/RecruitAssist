# RecruitAssist frontend

The RecruitAssist web app: a Next.js App Router project in TypeScript, styled with the Fieryfusion brand kit (light theme, corporate profile) and charts drawn with Recharts.

## How it talks to the backend

- `lib/api.ts` is the only file that calls the backend. Each route has one small typed function built on `request()`, which uses plain `fetch` and adds the `X-Demo-User` header.
- `lib/user.ts` reads and writes the `demo_user` cookie that holds the current demo user ID.
- `next.config.ts` rewrites `/api/*` to `${BACKEND_URL}/api/*`. Locally `BACKEND_URL` defaults to `http://localhost:8000`.
- A 401 sends the person to `/` to pick a demo user. A 404, including a record outside the user's scope, shows the not-found page.
- Pages render what the API returns and never compute a number.

Switching demo users is a demo feature, not authentication. The backend decides each user's role and scope on every request.

## Run it

The brand kit comes from GitHub Packages. `.npmrc` maps the `@suseelkrishna` scope there and reads a token from the `NPM_TOKEN` environment variable, so export a token with `read:packages` before installing.

```bash
export NPM_TOKEN=...   # a GitHub token with read:packages
npm ci
npm run dev            # http://localhost:3000, with the backend on http://localhost:8000
```

## Checks

```bash
npm run typecheck
npm run lint
```

## Pages

| Path | What it shows | API |
| --- | --- | --- |
| `/` | How it works, principles, and the demo users to pick from | `GET /api/users` |
| `/dashboard` | Filters, headline numbers, and eight charts, each with a table view | `GET /api/dashboard` |
| `/ask` | Questions to the assistant, with verified, cited answers | `GET /api/me`, `POST /api/ask` |
| `/jobs` | The jobs in scope, with filters kept in the URL | `GET /api/jobs` |
| `/jobs/[id]` | One job: funnel, ranked candidates, top 3, tasks, and reassignment | `GET /api/jobs/{id}`, `POST /api/jobs/{id}/assignment` |
