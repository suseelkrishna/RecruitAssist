# Running locally and deploying

The live site needs none of this. These steps are for running the code on your own machine or deploying your own copy.

## Local setup

The backend needs Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync
uv run python data/generate.py     # rebuilds data/recruiting.db, prints row counts
uv run pytest -q                   # runs the test suite
```

For live answers, copy `backend/.env.example` to `backend/.env` and add `ANTHROPIC_API_KEY`. Without a key the app uses recorded answers. Then start the API on http://localhost:8000:

```bash
cd backend
uv run uvicorn app.main:app --port 8000
```

Ask a question from the command line as any demo user. The CLI always answers live, so it needs `ANTHROPIC_API_KEY`:

```bash
cd backend
uv run python -m app.agent.cli "Which tasks are pending or overdue?" --user USR-4
```

Run the evals, which make paid API calls. `--estimate` measures one question per setting first:

```bash
cd backend
uv run python evals/run.py --estimate
uv run python evals/run.py --models claude-haiku-5-5 claude-sonnet-5-5 claude-opus-5-5
```

The frontend uses the FieryFusion brand kit, a private package on GitHub Packages. Export a GitHub token with `read:packages` access to it as `NPM_TOKEN`, then start the app on http://localhost:3000:

```bash
cd frontend
export NPM_TOKEN=...
npm ci
npm run dev
```

Without access to the brand kit, the backend, its tests, the CLI, and the evals all run locally, and the live demo shows the UI. See [frontend/README.md](../frontend/README.md) for the frontend checks.

To use the tools directly in Claude Code, which then acts as the Admin user, run this from the repository root:

```bash
claude mcp add recruitassist --scope user -- "$PWD/backend/.venv/bin/python" "$PWD/backend/app/mcp_server.py"
```

| Variable | Where | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | Backend | Turns on live answers |
| `ANTHROPIC_MODEL` | Backend | The model, default `claude-haiku-5-5` |
| `ANTHROPIC_EFFORT` | Backend | The thinking effort, default `low` |
| `OPENAI_API_KEY` | Backend, evals only | Lets `evals/run.py` run OpenAI models; the app ignores it |
| `ALLOW_OPENAI_LIVE` | Backend | Leave unset. `1` lets the app answer with an OpenAI model |
| `DAILY_LIVE_CAP` | Backend | Live answers per day across all users, default 150 |
| `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | Backend | Keep the change log, reassignments, rate limits, and saved chats in Upstash Redis. `KV_REST_API_URL` and `KV_REST_API_TOKEN`, the names the Vercel integration creates, work too |
| `BACKEND_URL` | Frontend | Where `/api/*` is forwarded, default `http://localhost:8000` |
| `NPM_TOKEN` | Frontend install | Reads the private brand kit |

## Deploying to Vercel

The app is hosted as two Vercel projects on the Hobby plan, both connected to this repository so that every merge to `main` deploys to production:

| Project | Root Directory | Preset | Environment variables |
|---|---|---|---|
| `recruitassist-api` | `backend/` | FastAPI | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `DAILY_LIVE_CAP`, `KV_REST_API_URL`, `KV_REST_API_TOKEN` (or the `UPSTASH_REDIS_REST_` names) |
| `recruitassist` | `frontend/` | Next.js | `BACKEND_URL`, `NPM_TOKEN` |

- **Backend.** Vercel runs the FastAPI app from `app/main.py` on Python 3.12 (`backend/.python-version`) and installs the pinned dependencies. `pyproject.toml` names the entrypoint explicitly. `backend/vercel.json` adds the database, the recorded answers, the eval and quality JSON files, and the test files (the quality page counts them) to the function bundle.
- **Answer time.** One answer can take up to 6 model rounds, so `vercel.json` sets the function's maximum duration to 300 seconds. That is the current Hobby limit with Fluid compute; Pro allows up to 800 seconds.
- **Redis.** Upstash Redis, added from the Vercel Marketplace on its free tier, holds the change log, reassignments, rate limits, and saved Ask chats. Connecting it to `recruitassist-api` adds the `KV_REST_API_URL` and `KV_REST_API_TOKEN` variables, which the backend reads through the Upstash REST API. Without it the store lives in memory and resets whenever the function restarts.
- **Saved chats.** Each demo user's Ask chats are kept for 30 days after their last change, at most 50 per user (the oldest is dropped) and 30 questions per chat. Emails and phone numbers are masked before a chat is saved, and only Admin chats keep the trace. With the in-memory store they reset when the function restarts, and the Admin's chat list says so.
- **Frontend.** `next.config.ts` forwards `/api/:path*` to `${BACKEND_URL}/api/:path*`. The browser only talks to the frontend's domain, so the backend needs no CORS setup. `NPM_TOKEN` must be available at build time. Use a classic GitHub token with only the `read:packages` scope; `frontend/.npmrc` reads it to install the brand kit.
- **Secrets.** Only the backend sees `ANTHROPIC_API_KEY` and the Redis token. No `NEXT_PUBLIC_*` variable is secret, and the root `.vercelignore` keeps local `.env` files out of CLI uploads.
- **Spending.** Set a monthly spend limit for the API key's workspace in the Anthropic Console. The rate limits bound normal use, and the spend limit is the backstop if they are misconfigured.

