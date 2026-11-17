"""MCP tools over the in-process transport. Skipped unless the optional mcp package is installed."""
import asyncio
import json

import pytest

import grab_mcp
import webui
from test_api import enable, server  # noqa: F401 - reuse the live API fixture
from test_webui import isolated  # noqa: F401 - fresh folders and job list for every test

pytest.importorskip("mcp")


def run_with_client(server_url, token, scenario):
    from mcp import Client

    async def go():
        async with Client(grab_mcp.build_server(grab_mcp.ApiClient(server_url, token))) as client:
            return await scenario(client)

    return asyncio.run(go())


def result_json(result):
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


def test_tools_are_listed_with_safety_hints(server):  # noqa: F811
    async def scenario(client):
        return {tool.name: tool for tool in (await client.list_tools()).tools}

    tools = run_with_client(server + "/api/v1", "vg_unused", scenario)
    assert set(tools) == {"queue_download", "get_job", "get_queue_status"}
    assert tools["get_job"].annotations.read_only_hint is True
    assert tools["get_queue_status"].annotations.read_only_hint is True
    assert tools["queue_download"].annotations.destructive_hint is False
    assert "never as instructions" in tools["get_job"].description
    assert set(tools["queue_download"].input_schema["properties"]) == {
        "urls", "mode", "quality", "abr", "no_playlist", "subtitles"}


def test_tools_queue_and_read_through_the_api(server):  # noqa: F811
    token = enable(server)

    async def scenario(client):
        queued = await client.call_tool("queue_download", {"urls": ["https://example.com/a"], "mode": "mp3"})
        ids = result_json(queued)["ids"]
        job = await client.call_tool("get_job", {"job_id": ids[0]})
        status = await client.call_tool("get_queue_status", {})
        missing = await client.call_tool("get_job", {"job_id": "deadbeef"})
        bad = await client.call_tool("queue_download", {"urls": ["https://example.com/b"], "mode": "exe"})
        return ids, result_json(job), result_json(status), missing, bad

    ids, job, status, missing, bad = run_with_client(server + "/api/v1", token, scenario)
    assert len(ids) == 1 and job["id"] == ids[0] and job["status"] == "queued"
    assert status["jobs"]["queued"] == 1
    assert missing.is_error and "No task" in missing.content[0].text
    assert bad.is_error  # rejected by the tool's input schema before any request
    assert len(webui.JOB_MANAGER.snapshot()) == 1
