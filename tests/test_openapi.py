"""docs/openapi.json must describe what /api/v1 actually accepts and returns."""
import json
from pathlib import Path

import grab_api
import webui
from test_api import bearer, enable, send, server  # noqa: F401 - reuse the live API fixture
from test_webui import isolated  # noqa: F401 - fresh folders and job list for every test

SPEC = json.loads((Path(__file__).resolve().parents[1] / "docs" / "openapi.json").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]


def assert_matches(value, schema):
    """Every required field is present and no undocumented field appears."""
    assert set(schema["required"]) <= set(value), set(schema["required"]) - set(value)
    assert set(value) <= set(schema["properties"]), set(value) - set(schema["properties"])


def test_spec_lists_exactly_the_routes_the_server_handles():
    assert set(SPEC["paths"]) == {"/downloads", "/jobs/{id}", "/status"}
    assert SPEC["servers"][0]["url"].startswith("http://127.0.0.1:")


def test_request_schema_matches_the_validator():
    request = SCHEMAS["DownloadRequest"]
    assert request["additionalProperties"] is False
    assert set(request["properties"]) == {"urls", "mode", "quality", "abr", "no_playlist", "subtitles"}
    assert request["properties"]["mode"]["enum"] == list(grab_api.MODES)
    assert request["properties"]["abr"]["enum"] == list(grab_api.ABR)
    assert request["properties"]["urls"]["oneOf"][1]["maxItems"] == grab_api.MAX_URLS
    # An undocumented field is rejected by the server too.
    try:
        grab_api.download_request({"urls": ["https://example.com/a"], "folder": "C:/"})
    except ValueError as error:
        assert "Unsupported fields" in str(error)
    else:
        raise AssertionError("undocumented field accepted")


def test_live_responses_match_the_documented_schemas(server):  # noqa: F811
    token = enable(server)
    status, body = send(server, "/api/v1/downloads", {"urls": ["https://example.com/a"]}, bearer(token))
    assert status == 202
    assert_matches(body, SCHEMAS["QueuedResponse"])
    status, job = send(server, f"/api/v1/jobs/{body['ids'][0]}", headers=bearer(token))
    assert status == 200
    assert_matches(job, SCHEMAS["Job"])
    assert job["status"] in SCHEMAS["Job"]["properties"]["status"]["enum"]
    status, queue = send(server, "/api/v1/status", headers=bearer(token))
    assert status == 200
    assert_matches(queue, SCHEMAS["Status"])
    assert set(queue["jobs"]) == set(SCHEMAS["Status"]["properties"]["jobs"]["required"])
    status, error = send(server, "/api/v1/jobs/deadbeef", headers=bearer(token))
    assert status == 404
    assert_matches(error, SCHEMAS["Error"])
    assert webui.JOB_MANAGER.get(body["ids"][0]) is not None
