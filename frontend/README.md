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
npm test               # component tests (Vitest and Testing Library in jsdom)
```

The Playwright smoke tests start the backend (recorded answers only, no API key) and the dev server, or reuse ones already running on ports 8000 and 3000. They pick each demo user, open every page the role allows, check that the others show not found, open the catch-up tiles from the keyboard at 1280 and 390 pixels wide, open the full dashboard, ask one suggested question against a stubbed `/api/ask`, and complete one reassignment.

```bash
npx playwright install chromium   # once
npm run e2e
```

`PW_REPORT_DIR` and `PW_OUTPUT_DIR` move the HTML report and test output, for example outside the repo. `PLAYWRIGHT_CHROMIUM_PATH` points at an already installed Chromium instead of the bundled one.

## Pages

| Path | What it shows | API |
| --- | --- | --- |
| `/` | The RecruitAssist mark, one line on what it does, and the demo users to pick from. How it works opens in a drawer | `GET /api/users` |
| `/dashboard` | The catch-up view: a greeting, one line on what needs attention, and five tiles that open their chart or task list on click | `GET /api/catch-up`, then `GET /api/dashboard` when a chart tile opens |
| `/dashboard?view=full` | The full dashboard: filters, headline numbers, and eight charts, each with a table view | `GET /api/dashboard` |
| `/ask` | Questions to the assistant, with verified, cited answers | `GET /api/me`, `POST /api/ask` |
| `/jobs` | The jobs in scope, with filters kept in the URL | `GET /api/jobs` |
| `/jobs/[id]` | One job: funnel, ranked candidates, top 3, tasks, and reassignment | `GET /api/jobs/{id}`, `POST /api/jobs/{id}/assignment` |
| `/tasks` | Pending and overdue tasks, grouped by team (Admin) or recruiter (HR Manager), explicit or derived | `GET /api/tasks` |
| `/candidates/[applicationId]` | The full evidence for one application, the same view as the Ask drawer | `GET /api/candidates/{id}` |
| `/sources` | Live checks, integrations (marked Simulated), and candidate sources. Admin and HR Manager | `GET /api/sources`, `GET /api/health` |
| `/changes` | The append-only change log of reassignments and questions. Admin and HR Manager | `GET /api/changes` |
| `/quality` | Test counts, mutation score, access matrix, and the eval scoreboard, when reports exist | `GET /api/quality` |
