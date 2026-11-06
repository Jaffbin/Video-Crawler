import io
import types

import pytest

import webui
from test_webui import isolated, server, call  # noqa: F401


def handler_for(body=b"{}", length="2"):
    handler = object.__new__(webui.Handler)
    handler.command = "POST"
    handler.headers = {"Content-Length": length, "Host": "127.0.0.1"}
    handler.rfile = io.BytesIO(body)
    timeouts = []
    handler.connection = types.SimpleNamespace(gettimeout=lambda: None, settimeout=timeouts.append)
    return handler, timeouts


@pytest.mark.parametrize("forbidden_host", [False, True])
def test_rejected_post_discards_body_before_response_without_dispatch(forbidden_host):
    handler, timeouts = handler_for()
    if forbidden_host:
        handler.headers["Host"] = "untrusted.invalid"
    responses = []

    def respond(body, status):
        assert handler.rfile.tell() == 2
        responses.append(status)

    handler._json = respond
    assert (handler._guard() if forbidden_host else handler._authed({})) is False
    assert responses == [403 if forbidden_host else 401]
    assert handler.close_connection is True
    assert 0 < timeouts[0] <= 1 and timeouts[-1] is None


@pytest.mark.parametrize("length", ["0", "-1", "invalid", str(webui.BODY_MAX_BYTES + 1)])
def test_rejected_body_is_bounded(length):
    handler, timeouts = handler_for(length=length)
    handler._discard_rejected_body()
    assert handler.rfile.tell() == 0 and not timeouts


def test_rejected_body_timeout_restores_connection_settings():
    handler, timeouts = handler_for()

    def timeout(amount):
        raise TimeoutError("Client did not finish sending")

    handler.rfile = types.SimpleNamespace(read1=timeout)
    handler._discard_rejected_body()
    assert timeouts[-1] is None and handler.close_connection is True


def test_unauthorized_posts_return_response_and_leave_library_unchanged(server):  # noqa: F811
    for _ in range(20):
        status, body = call(server, "/api/library/smart-collections", {
            "action": "create", "name": "Denied", "rules": {"favorite": True},
        }, token=False)
        assert status == 401 and "Unauthorized" in body["error"]
    assert webui.LIBRARY.smart_collections() == []
