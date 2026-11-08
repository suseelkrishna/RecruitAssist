"""The MCP server: annotations, strict schemas, the per-request principal, resource, and prompts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from app import access
from app import mcp_server

pytestmark = pytest.mark.anyio

EXPECTED_TOOLS = {"list_jobs", "pipeline_by_job", "funnel_dropoff", "score_candidates",
                  "get_candidate_evidence", "pending_tasks", "source_quality", "recruiter_load",
                  "integration_health"}


@pytest.fixture
def anyio_backend():
    """Run the async tests on asyncio."""
    return "asyncio"


def payload(result) -> dict:
    """The JSON a tool returned."""
    return json.loads(result.content[0].text)


async def call_as(user_id: str, tool: str, args: dict | None = None):
    """Call one tool through an in-process client with the principal set for that user."""
    token = access.current_principal.set(access.principal_for(user_id))
    try:
        async with Client(mcp_server.mcp) as client:
            return await client.call_tool(tool, args or {})
    finally:
        access.current_principal.reset(token)


async def test_tools_are_read_only_and_strict():
    async with Client(mcp_server.mcp) as client:
        tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == EXPECTED_TOOLS
    for tool in tools:
        hints = tool.annotations
        assert (hints.read_only_hint, hints.idempotent_hint, hints.open_world_hint) == (True, True, False)
        assert tool.input_schema["additionalProperties"] is False
        assert not {"principal", "user_id", "role"} & set(tool.input_schema.get("properties", {}))


async def test_the_principal_comes_from_the_context_variable():
    admin = payload(await call_as("USR-1", "list_jobs"))
    recruiter = payload(await call_as("USR-6", "list_jobs"))
    assert admin["count"] == 7
    assert [j["job_id"] for j in recruiter["jobs"]] == ["JOB-3", "JOB-6"]


async def test_out_of_scope_fails_closed_through_the_tool():
    result = await call_as("USR-6", "score_candidates", {"job_id": "JOB-2"})
    assert result.is_error and "JOB-2 is not in your scope" in result.content[0].text


async def test_unknown_arguments_are_rejected():
    result = await call_as("USR-6", "list_jobs", {"principal": "USR-1"})
    assert result.is_error and "Extra inputs are not permitted" in result.content[0].text


async def test_malformed_ids_are_rejected_by_the_schema():
    result = await call_as("USR-1", "pipeline_by_job", {"job_id": "JOB-1' OR 1=1"})
    assert result.is_error and "pattern" in result.content[0].text


async def test_no_principal_fails_closed():
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("list_jobs", {})
    assert result.is_error and "No user is set" in result.content[0].text


async def test_rubric_resource_and_prompts():
    async with Client(mcp_server.mcp) as client:
        rubric = await client.read_resource("rubric://scoring/v1")
        prompts = {p.name for p in (await client.list_prompts()).prompts}
        triage = await client.get_prompt("task_triage", {})
        top = await client.get_prompt("top_candidates", {"job": "Manufacturing Process Engineer"})
    assert json.loads(rubric.contents[0].text)["weights"] == {"scorecards": 0.5, "must_have": 0.3, "stage": 0.2}
    assert prompts == {"top_candidates", "funnel_leaks", "task_triage"}
    assert "pending_tasks" in triage.messages[0].content.text
    assert "Manufacturing Process Engineer" in top.messages[0].content.text


async def test_stdio_entry_point_runs_as_admin():
    script = Path(mcp_server.__file__).resolve()
    params = StdioServerParameters(command=sys.executable, args=[str(script)], cwd=str(script.parent))
    async with Client(params) as client:
        result = await client.call_tool("list_jobs", {})
    assert payload(result)["count"] == 7
