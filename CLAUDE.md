# RecruitAssist

A recruiting assistant that answers a recruiter's questions about a hiring pipeline. Claude calls read-only MCP tools over a synthetic SQLite database and explains the results with citations. A deterministic verifier checks each answer before the recruiter sees it. The app also includes a role-scoped dashboard, job lists, and a change log.

## Core principle

- Tools compute every number and fetch evidence with stable IDs.
- The model picks tools, explains the results, and flags missing data.
- The verifier checks numbers, citations, and ranking order.
- People make the hiring decisions. The agent has no write tools.

## Code style (most important rule)

The codebase should be easy to read and explain end to end.

- Write the plainest code that works: plain functions, plain SQL, and plain `fetch`.
- No frameworks beyond Next.js and FastAPI. That means no ORM, no state library, no agent framework, no dependency-injection container, and no speculative abstractions.
- One concept per file. Every function gets a short docstring explaining what it does and why.
- Discuss any new dependency or pattern before adding it.

## Repo structure

```
frontend/                     Next.js App Router + TypeScript (Vercel project 1)
  app/                        one folder per page: (landing) dashboard ask jobs tasks sources changes quality
  components/                 small UI pieces built on the brand kit
  lib/api.ts                  the ONLY place that calls the backend
  lib/user.ts                 current demo user (cookie), sent as the X-Demo-User header
backend/                      FastAPI + Python 3.12 + uv (Vercel project 2)
  app/main.py                 FastAPI app and routes (thin: parse, call logic, return JSON)
  app/access.py               Principal: who the demo user is and which job IDs they may see
  app/db.py                   the only file that opens SQLite (read-only)
  app/store.py                the small writable store: change log, assignment changes, rate limits (Redis or in-memory)
  app/logic/                  pure functions: scoring.py funnel.py tasks.py analytics.py sources.py scope.py
  app/mcp_server.py           MCP tools, resource, prompts wrapping app/logic (stdio entry for Claude Code)
  app/agent/loop.py           the agent loop (MCP client over the in-memory transport)
  app/agent/prompt.py         frozen system prompt
  app/agent/verify.py         number, citation, ranking, and PII checks
  app/agent/cli.py            python -m app.agent.cli "question"
  app/llm/                    the LLM interface: Anthropic and OpenAI adapters, models.yaml (providers and prices)
  data/                       generate.py, schema.sql, recruiting.db (committed), recordings.json
  evals/                      expected.py, questions.yaml, run.py, grade.py, judge.py, judge_rubric.md,
                              report.py, results.md, scoreboard.json (raw runs go to evals_out/, ignored)
  tests/
README.md
CLAUDE.md
```

How a request flows. Use this path when explaining any feature:

1. A page in `frontend/app/`
2. A function in `frontend/lib/api.ts`
3. A route in `backend/app/main.py`
4. A pure function in `backend/app/logic/`
5. A query in `backend/app/db.py`

Ask follows a slightly different path: from `main.py` it goes to `agent/loop.py`, then to the MCP tools, and from there into the same `logic/` functions.

## Stack

- **Backend:** Python 3.12 with `uv`, FastAPI, `mcp` 2.3.0, the `anthropic` SDK, and pytest. The `openai` SDK is an eval-only dependency (uv group `evals`), used to compare OpenAI models; the app ships Claude only. In `mcp` 2.3.0 the server class is `MCPServer`, formerly called `FastMCP`. Check the current SDK docs before writing SDK code; never guess signatures.
- **Frontend:** Next.js App Router with TypeScript and Recharts. It uses the `@suseelkrishna/fieryfusion-tokens` and `@suseelkrishna/fieryfusion-react` packages from GitHub Packages, with the light theme and the corporate profile.
- **Hosting:** two Vercel Hobby projects from this repo, with Root Directory set to `frontend/` and `backend/`. The frontend rewrites `/api/*` to `BACKEND_URL`.
- **Model:** `ANTHROPIC_MODEL`, default `claude-haiku-5-5` at effort `low` (`ANTHROPIC_EFFORT`), chosen by the evals in `backend/evals/results.md`.
  - Use adaptive thinking and set `output_config.effort` explicitly.
  - Never send `temperature`, `top_p`, or `top_k`.
  - Never force `tool_choice`; use `auto`.

## Commands

```bash
cd backend && uv sync && uv run python data/generate.py && uv run pytest -q
cd backend && uv run fastapi dev app/main.py                 # http://localhost:8000
cd backend && uv run python -m app.agent.cli "Which tasks are pending or overdue?"
cd backend && uv run python evals/run.py --models claude-haiku-5-5 claude-sonnet-5-5 claude-opus-5-5
cd backend && uv run python evals/run.py --models gpt-6-luna gpt-6.1-terra gpt-6.1-sol --resume evals_out/<stamp>/runs.jsonl
cd frontend && npm ci && npm run dev                         # http://localhost:3000, needs NPM_TOKEN for the brand kit
claude mcp add recruitassist --scope user -- "$PWD/backend/.venv/bin/python" "$PWD/backend/app/mcp_server.py"
```

## Rules

**Data**
- All data is invented. The company is Northbeam Robotics, a fictional company, with invented people, schools, and employers.
- Emails use only `example.com` and phone numbers only `555-01xx`.
- Never include protected attributes.
- The database is read-only. Open it with `mode=ro`, use only parameterized SQL, and never add a generic SQL tool.
- Times are UTC. Every function takes an optional `as_of`, which defaults to `meta.as_of`.

**Roles and access**
- There are three roles: `admin`, `hr_manager`, and `hr_user`.
- The frontend sends the demo user ID, and the backend turns it into a `Principal` with `allowed_job_ids`.
- Every logic function and tool filters by `allowed_job_ids` inside SQL.
- The principal is never a tool argument and the model never sees it.
- Hiding something in the UI is not access control. Out-of-scope requests fail closed.
- There are no passwords. Switching demo users is a demo feature, not authentication, and the README says so.

**Writes**
- The only write is reassigning a job's recruiter. Admin can reassign any job; an HR Manager can reassign jobs on their own teams.
- A reassignment needs a confirmation in the UI and adds an entry to the append-only change log.
- The agent can never write.

**Tools**
- Tools return compact JSON with IDs like `APP-014`, `SC-031`, `EM-007`, `TASK-012`, and `JOB-2`.
- Free text is wrapped as `{"untrusted_text": ...}` and contact details are masked.
- Include `warnings` and `missing` fields where they apply.
- Errors are helpful: `ToolError` messages list the valid options.

**Metrics**
- Metrics live only in `backend/app/logic/`. The frontend never computes a number.
- The dashboard and the agent use the same functions.

**Testing**
- Every behavior change ships with a test.
- Tests stay independent of the code under test, for example SQL written separately or hand-computed fixtures.

**Secrets and committed files**
- Keep secrets out of code, logs, and the browser. Only `NEXT_PUBLIC_*` variables reach the browser, and none of them are secret.
- Never commit `.env*` files, eval transcripts, or caches. The one generated file that is committed is `backend/data/recruiting.db`, because it is deterministic.

**Writing and repo hygiene**
- UI copy and docs are in plain English for non-technical readers. Never use em dashes anywhere.
- Comments and docs describe what the code does and why, in a neutral, factual tone. Track open work in issues, not in code comments, and leave out references to work plans, schedules, or internal notes.
- The repo holds only code and user-facing docs: no planning notes, task lists, or scratch files. The README is the only design write-up.

**Commits**
- Use Conventional Commits: `type(scope): summary`, for example `feat(scoring): rank applications by scorecard evidence`. Types are `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, and `chore`.
- The subject is in the imperative mood, at most 72 characters, with no trailing period. The body is a few short bullets on what changed and why.
- Each commit is one logical change.
- Do not run `git commit` or `git push`. Propose the commit message and leave the changes for review.
