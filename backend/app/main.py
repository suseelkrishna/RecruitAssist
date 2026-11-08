"""The RecruitAssist HTTP API. Each route parses the request, calls logic, and returns JSON.

Identity: every route except /api/health and /api/users reads the X-Demo-User
header and builds a Principal from it on the server. A missing or unknown user
gets a 401. The client never sends a role or scope. Switching demo users is a
demo feature, not authentication.

Errors come back as JSON with an "error" message: 404 for an ID outside the
user's scope (the same as an ID that does not exist), 403 for an action the
role does not allow, 400 for a bad value, 422 for a malformed request, and 500
for anything unexpected, without a stack trace.

    uv run fastapi dev app/main.py
"""

from __future__ import annotations

import hashlib
import os
from typing import Annotated, Any

import anthropic
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import access, checks, quality, store
from app.access import Principal
from app.agent import loop, recordings
from app.env import load_env_file
from app.logic import analytics, assignments, evidence, scope, sources, tasks
from app.logic.common import NotAllowedError, OutOfScopeError, require_job

load_env_file()

ASK_LIMIT_PER_IP_PER_HOUR = 10
DEFAULT_DAILY_LIVE_CAP = 150
HOUR = 3600
DAY = 86400

JobId = Annotated[str, Path(pattern=r"^JOB-\d+$")]
ApplicationId = Annotated[str, Path(pattern=r"^APP-\d+$")]
DateParam = r"^\d{4}-\d{2}-\d{2}$"

app = FastAPI(title="RecruitAssist API", docs_url="/api/docs", openapi_url="/api/openapi.json")


class AssignmentBody(BaseModel):
    """The body of a reassignment: the recruiter who should own the job."""

    model_config = ConfigDict(extra="forbid")
    recruiter_user_id: str = Field(pattern=r"^USR-\d+$")


class HistoryItem(BaseModel):
    """One earlier question and answer in the conversation."""

    model_config = ConfigDict(extra="forbid")
    question: str = Field(max_length=1000)
    answer: str = Field(max_length=8000)


class AskBody(BaseModel):
    """The body of a question to the agent."""

    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)
    job_id: str | None = Field(default=None, pattern=r"^JOB-\d+$")
    history: list[HistoryItem] = Field(default_factory=list, max_length=20)


def error(status: int, message: str, **extra: Any) -> JSONResponse:
    """A JSON error response with a friendly message."""
    return JSONResponse(status_code=status, content={"error": message, **extra})


@app.exception_handler(OutOfScopeError)
def out_of_scope(_: Request, exc: OutOfScopeError) -> JSONResponse:
    """An ID outside the user's scope is reported as not found, so its existence stays hidden."""
    return error(404, str(exc))


@app.exception_handler(NotAllowedError)
def not_allowed(_: Request, exc: NotAllowedError) -> JSONResponse:
    """The user can see the record but their role does not allow the action."""
    return error(403, str(exc))


@app.exception_handler(ToolError)
def bad_value(_: Request, exc: ToolError) -> JSONResponse:
    """A value the logic rejected, with a message that lists the valid options."""
    return error(400, str(exc))


@app.exception_handler(RequestValidationError)
def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    """A malformed request: which fields are wrong and why, without internals."""
    details = [{"field": ".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]), "message": e["msg"]}
               for e in exc.errors()]
    return error(422, "Some of the request is not valid.", details=details)


@app.exception_handler(StarletteHTTPException)
def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Errors raised by the routes themselves, such as a missing demo user."""
    return error(exc.status_code, str(exc.detail))


@app.exception_handler(Exception)
def unexpected(_: Request, exc: Exception) -> JSONResponse:
    """Anything unexpected: a generic message and no stack trace."""
    return error(500, "Something went wrong on our side. Try again in a moment.")


def principal(x_demo_user: Annotated[str | None, Header()] = None) -> Principal:
    """The Principal for the X-Demo-User header. 401 when the header is missing or unknown."""
    if not x_demo_user:
        raise HTTPException(401, "Choose a demo user first. Send their ID in the X-Demo-User header.")
    try:
        return access.principal_for(x_demo_user)
    except LookupError as exc:
        raise HTTPException(401, str(exc)) from None


def model_client() -> Any:
    """The Messages API client, or None when no API key is set (answers then come from recordings)."""
    return loop.make_client() if os.environ.get("ANTHROPIC_API_KEY") else None


User = Annotated[Principal, Depends(principal)]


@app.get("/api/health")
def health() -> dict[str, str]:
    """A liveness check that needs no user."""
    return {"status": "ok"}


@app.get("/api/users")
def users() -> dict[str, Any]:
    """The demo users for the user switcher. Public: it lists names and roles only."""
    return {"users": access.demo_users()}


@app.get("/api/me")
def me(user: User) -> dict[str, Any]:
    """Who the current demo user is and their scope card."""
    return {"user": {"user_id": user.user_id, "name": user.name, "role": user.role},
            "allowed_job_ids": sorted(user.allowed_job_ids), "team_ids": sorted(user.team_ids),
            "scope": scope.scope_card(user)}


@app.get("/api/dashboard")
def dashboard(user: User,
              team: Annotated[str | None, Query(pattern=r"^TEAM-\d+$")] = None,
              job: Annotated[str | None, Query(pattern=r"^JOB-\d+$")] = None,
              recruiter: Annotated[str | None, Query(pattern=r"^USR-\d+$")] = None,
              date_from: Annotated[str | None, Query(alias="from", pattern=DateParam)] = None,
              date_to: Annotated[str | None, Query(alias="to", pattern=DateParam)] = None) -> dict[str, Any]:
    """Every dashboard metric for the filters, in one response."""
    return analytics.dashboard(user, team_id=team, job_id=job, recruiter_user_id=recruiter,
                               date_from=date_from, date_to=date_to)


@app.get("/api/jobs")
def jobs(user: User) -> dict[str, Any]:
    """The jobs in the user's scope."""
    return scope.list_jobs(user)


@app.get("/api/jobs/{job_id}")
def job(user: User, job_id: JobId) -> dict[str, Any]:
    """One job, with can_reassign and the recruiters it may go to. 404 when out of scope."""
    return assignments.job_detail(user, job_id)


@app.post("/api/jobs/{job_id}/assignment")
def reassign(user: User, job_id: JobId, body: AssignmentBody) -> dict[str, Any]:
    """Reassign the job's recruiter, record the change, and return the updated job."""
    return assignments.reassign(user, job_id, body.recruiter_user_id)


@app.get("/api/tasks")
def pending(user: User,
            owner: Annotated[str | None, Query(pattern=r"^USR-\d+$")] = None,
            job: Annotated[str | None, Query(pattern=r"^JOB-\d+$")] = None) -> dict[str, Any]:
    """Open and derived tasks in scope, most overdue first."""
    return tasks.pending_tasks(user, owner_user_id=owner, job_id=job)


@app.get("/api/candidates/{application_id}")
def candidate(user: User, application_id: ApplicationId) -> dict[str, Any]:
    """The evidence for one application, contact details masked. 404 when out of scope."""
    return evidence.get_candidate_evidence(user, application_id)


@app.get("/api/sources")
def source_health(user: User) -> dict[str, Any]:
    """Integration health, source quality for the user's scope, and the live checks."""
    return {"integrations": sources.integration_health()["integrations"],
            "source_quality": analytics.source_quality(user),
            "checks": checks.live_checks()}


@app.get("/api/changes")
def changes(user: User) -> dict[str, Any]:
    """The change log entries the user may see, newest first."""
    return {"changes": store.list_changes(user)}


@app.get("/api/quality")
def quality_page(user: User) -> dict[str, Any]:
    """Test counts, mutation score, RBAC result, and the eval scoreboard."""
    return quality.quality_report()


@app.post("/api/ask")
async def ask(user: User, body: AskBody, request: Request,
              client: Annotated[Any, Depends(model_client)]) -> Any:
    """Run the agent and return the full result with source live or recording.

    Live answers are limited to ASK_LIMIT_PER_IP_PER_HOUR per IP and DAILY_LIVE_CAP per
    day overall. Past a limit, or without an API key, a matching recording is returned
    if there is one. Each answered question adds a change event holding a hash of the
    question, the tools used, and the cited record IDs, never candidate text.
    """
    if body.job_id is not None:
        require_job(user, body.job_id)
    history = [h.model_dump() for h in body.history]
    limited = (store.hit_rate_limit(f"ask:ip:{client_ip(request)}", ASK_LIMIT_PER_IP_PER_HOUR, HOUR)
               or store.hit_rate_limit("ask:all", daily_live_cap(), DAY))
    result = None
    if client is not None and not limited:
        try:
            result = await loop.run_agent(body.question, user, job_id=body.job_id, history=history,
                                          client=client)
        except anthropic.APIError:
            result = None
    if result is None:
        result = recordings.find(body.question, user.user_id, body.job_id, sorted(user.allowed_job_ids))
    if result is None:
        if limited:
            return error(429, "You have reached the limit for live answers. Try again later, or ask one "
                              "of the suggested questions, which have recorded answers.")
        return error(503, "Live answers are not available right now. Try one of the suggested questions, "
                          "which have recorded answers.")
    store.append_change({
        "type": "ask",
        "user_id": user.user_id,
        "job_id": body.job_id,
        "question_sha256": hashlib.sha256(body.question.encode()).hexdigest(),
        "tools": sorted({s["tool"] for s in result["steps"]}),
        "record_ids": result["citations"],
        "source": result["source"],
        "verified": result["verified"],
    })
    return result


def client_ip(request: Request) -> str:
    """The caller's IP: the first X-Forwarded-For entry set by the hosting proxy, else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def daily_live_cap() -> int:
    """The most live answers per day across all users: DAILY_LIVE_CAP, default 150."""
    try:
        return int(os.environ.get("DAILY_LIVE_CAP", DEFAULT_DAILY_LIVE_CAP))
    except ValueError:
        return DEFAULT_DAILY_LIVE_CAP
